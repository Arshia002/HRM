import contextlib
import shutil
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

from sazmanhr.api_client import ApiClient, ApiError
from sazmanhr.database import Repository
from sazmanhr.server import ApiServer


ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "data" / "seed" / "sazmanhr-seed.sqlite"


class G10HrWorkflowAcceptanceTests(unittest.TestCase):
    def test_core_hr_daily_workflow_is_end_to_end_audited_and_reversible(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            database = root / "hrm.sqlite"
            shutil.copy2(SEED, database)
            repo = Repository(database)

            owner_password = "G10!Owner1500"
            hr_password = "G10!HrAdmin1500"
            owner = repo.create_user(
                "g10.owner",
                "G10 Super Admin",
                owner_password,
                "owner",
                must_change_password=False,
            )
            hr = repo.create_user(
                "g10.hr",
                "G10 HR Admin",
                hr_password,
                "admin",
                must_change_password=False,
            )

            # Pick a person that already has a primary assignment so this
            # scenario proves assignment closure/history, not only creation.
            assigned = None
            for item in repo.list_personnel(limit=100)["items"]:
                detail = repo.get_person(item["id"])
                if detail.get("assignment"):
                    assigned = detail
                    break
            self.assertIsNotNone(assigned)
            person_id = assigned["id"]

            server = ApiServer(("127.0.0.1", 0), repo)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_address[1]}"
            hr_client = ApiClient(base)
            owner_client = ApiClient(base)

            try:
                hr_client.login("g10.hr", hr_password)
                owner_client.login("g10.owner", owner_password)

                # F-001: personnel lookup workflow.
                listing = hr_client.request(
                    "GET",
                    "/api/personnel",
                    query={"limit": 100},
                )
                listed_ids = {str(item["id"]) for item in listing["items"]}
                self.assertIn(str(person_id), listed_ids)

                # F-002: personnel detail workflow.
                detail = hr_client.request(
                    "GET",
                    f"/api/personnel/{person_id}",
                )
                self.assertEqual(str(detail["id"]), str(person_id))
                self.assertEqual(detail["personnel_no"], assigned["personnel_no"])

                # F-003: authorized non-structural personnel edit.
                original_activity = detail.get("activity_area", "")
                detail["activity_area"] = "G10-HR-ACCEPTANCE"
                edited = hr_client.request("POST", "/api/personnel", detail)
                self.assertEqual(edited["activity_area"], "G10-HR-ACCEPTANCE")
                self.assertGreater(edited["row_version"], detail["row_version"])

                current = hr_client.request(
                    "GET",
                    f"/api/personnel/{person_id}",
                )
                original_org_state = (
                    current.get("organizational_unit", ""),
                    current.get("position_code", ""),
                    current.get("position_title", ""),
                )
                old_assignment = current.get("assignment")
                self.assertIsNotNone(old_assignment)
                old_assignment_id = old_assignment["assignment_id"]

                # F-007: structural HR state cannot bypass the movement boundary.
                bypass = dict(current)
                bypass["organizational_unit"] = "G10-ILLEGAL-DIRECT-UNIT"
                with self.assertRaises(ApiError):
                    hr_client.request("POST", "/api/personnel", bypass)

                # F-004/F-005: approved unit/position assignment through a
                # personnel movement. The previous assignment must remain as
                # history and a new active primary assignment must exist.
                movement = hr_client.request(
                    "POST",
                    f"/api/personnel/{person_id}/movements",
                    {
                        "movement_type": "transfer",
                        "effective_date": "1405/11/01",
                        "order_no": "G10-ORDER-001",
                        "order_date": "1405/10/29",
                        "reason": "G10 acceptance transfer",
                        "organizational_unit": "G10 Destination Unit",
                        "position_code": "G10-POS-001",
                        "position_title": "G10 Destination Position",
                        "row_version": current["row_version"],
                    },
                )
                movement_id = movement["movement"]["id"]
                moved_person = movement["person"]
                self.assertEqual(
                    moved_person["organizational_unit"],
                    "G10 Destination Unit",
                )
                self.assertEqual(moved_person["position_code"], "G10-POS-001")

                with contextlib.closing(sqlite3.connect(database)) as conn:
                    old_end_date = conn.execute(
                        "SELECT end_date FROM personnel_assignments WHERE id=?",
                        (old_assignment_id,),
                    ).fetchone()
                    self.assertIsNotNone(old_end_date)
                    self.assertEqual(str(old_end_date[0]), "1405/11/01")
                    active_assignments = int(
                        conn.execute(
                            """SELECT COUNT(*) FROM personnel_assignments
                               WHERE person_id=? AND is_primary=1 AND end_date=''""",
                            (person_id,),
                        ).fetchone()[0]
                    )
                    total_assignments = int(
                        conn.execute(
                            "SELECT COUNT(*) FROM personnel_assignments WHERE person_id=?",
                            (person_id,),
                        ).fetchone()[0]
                    )
                self.assertEqual(active_assignments, 1)
                self.assertGreaterEqual(total_assignments, 2)

                # F-006: movement/history review keeps the event.
                history = hr_client.request(
                    "GET",
                    f"/api/personnel/{person_id}/movements",
                )
                matching = [
                    item
                    for item in history["items"]
                    if str(item["id"]) == str(movement_id)
                ]
                self.assertEqual(len(matching), 1)
                self.assertEqual(matching[0]["order_no"], "G10-ORDER-001")

                # F-007: HR Admin may perform the transfer but may not reverse
                # it. Super Admin may reverse it.
                with self.assertRaises(ApiError):
                    hr_client.request(
                        "POST",
                        f"/api/movements/{movement_id}/reverse",
                        {"reason": "G10 HR-admin forbidden reversal"},
                    )

                reversed_result = owner_client.request(
                    "POST",
                    f"/api/movements/{movement_id}/reverse",
                    {"reason": "G10 approved correction"},
                )
                self.assertTrue(reversed_result["movement"]["is_reversed"])
                self.assertEqual(
                    reversed_result["movement"]["reversal_reason"],
                    "G10 approved correction",
                )

                restored = owner_client.request(
                    "GET",
                    f"/api/personnel/{person_id}",
                )
                self.assertEqual(
                    (
                        restored.get("organizational_unit", ""),
                        restored.get("position_code", ""),
                        restored.get("position_title", ""),
                    ),
                    original_org_state,
                )
                # Reversal must not erase the earlier legitimate non-structural
                # HR edit.
                self.assertEqual(restored["activity_area"], "G10-HR-ACCEPTANCE")

                history_after = owner_client.request(
                    "GET",
                    f"/api/personnel/{person_id}/movements",
                )
                reversed_event = next(
                    item
                    for item in history_after["items"]
                    if str(item["id"]) == str(movement_id)
                )
                self.assertTrue(reversed_event["is_reversed"])

                # F-008: audit review contract. Actor, action, timestamp and
                # target object must all be present for HR and Super Admin
                # actions, and the chain must remain valid.
                with contextlib.closing(sqlite3.connect(database)) as conn:
                    rows = conn.execute(
                        """SELECT user_id,action,entity_type,entity_id,occurred_at
                           FROM audit_log
                           WHERE user_id IN (?,?)
                           ORDER BY id""",
                        (hr["id"], owner["id"]),
                    ).fetchall()

                    self.assertTrue(
                        any(
                            str(row[0]) == str(hr["id"])
                            and str(row[3]) == str(person_id)
                            and str(row[1]).strip()
                            and str(row[4]).strip()
                            for row in rows
                        )
                    )
                    self.assertTrue(
                        any(
                            str(row[0]) == str(owner["id"])
                            and str(row[3]) in {str(person_id), str(movement_id)}
                            and str(row[1]).strip()
                            and str(row[4]).strip()
                            for row in rows
                        )
                    )
                    self.assertEqual(
                        conn.execute("PRAGMA integrity_check").fetchone()[0],
                        "ok",
                    )
                    self.assertEqual(
                        conn.execute("PRAGMA foreign_key_check").fetchall(),
                        [],
                    )

                self.assertTrue(repo.verify_audit_chain())

                # Restore test fixture's non-structural value only to make the
                # expected business-state boundary explicit; the temporary DB
                # is discarded after the scenario.
                self.assertNotEqual(original_activity, "G10-HR-ACCEPTANCE")
            finally:
                for client in (hr_client, owner_client):
                    try:
                        client.logout()
                    except Exception:
                        pass
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
