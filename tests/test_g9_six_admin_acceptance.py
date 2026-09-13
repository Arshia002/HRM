import contextlib
import shutil
import sqlite3
import ssl
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ci.release_identity import load_identity
from sazmanhr.api_client import ApiClient, ApiError
from sazmanhr.database import Repository
from sazmanhr.server import ApiServer
from sazmanhr.tls import ensure_self_signed_certificate


ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "data" / "seed" / "sazmanhr-seed.sqlite"


def _start_tls(repo: Repository, root: Path):
    cert, key, fingerprint = ensure_self_signed_certificate(root)
    server = ApiServer(("127.0.0.1", 0), repo, tls_enabled=True)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, fingerprint


class G9SixAdminAcceptanceTests(unittest.TestCase):
    def test_two_super_admin_four_hr_admin_concurrent_rbac_and_audit(self):
        identity = load_identity()
        deployment = identity.metadata.get("deployment_profile")
        self.assertIsInstance(deployment, dict)
        self.assertEqual(
            deployment.get("roles"),
            {"super_admin": 2, "hr_admin": 4},
        )

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            database = root / "hrm.sqlite"
            shutil.copy2(SEED, database)
            repo = Repository(database)
            password = "G9!SixAdmin1500"

            # Product role mapping:
            # owner = Super Admin; admin = HR Admin.
            users = [
                repo.create_user(
                    "g9.super.1", "G9 Super 1", password, "owner",
                    must_change_password=False,
                ),
                repo.create_user(
                    "g9.super.2", "G9 Super 2", password, "owner",
                    must_change_password=False,
                ),
            ]
            users.extend(
                repo.create_user(
                    f"g9.hr.{index}", f"G9 HR {index}", password, "admin",
                    must_change_password=False,
                )
                for index in range(1, 5)
            )

            self.assertEqual(sum(user["role"] == "owner" for user in users), 2)
            self.assertEqual(sum(user["role"] == "admin" for user in users), 4)

            server, thread, fingerprint = _start_tls(repo, root)
            base = f"https://127.0.0.1:{server.server_address[1]}"
            clients = [
                ApiClient(base, tls_fingerprint=fingerprint)
                for _ in range(6)
            ]

            try:
                for client, user in zip(clients, users):
                    client.login(user["username"], password)

                people = clients[0].request(
                    "GET", "/api/personnel", query={"limit": 8}
                )["items"]
                self.assertGreaterEqual(len(people), 8)

                # Six authenticated users make six independent writes at once.
                def independent_write(args):
                    index, client, user = args
                    person_id = people[index]["id"]
                    detail = client.request("GET", f"/api/personnel/{person_id}")
                    detail["activity_area"] = f"G9-ACTOR-{user['id']}"
                    saved = client.request("POST", "/api/personnel", detail)
                    return user["id"], person_id, saved["row_version"]

                with ThreadPoolExecutor(max_workers=6) as pool:
                    writes = list(
                        pool.map(
                            independent_write,
                            [
                                (index, client, user)
                                for index, (client, user) in enumerate(
                                    zip(clients, users)
                                )
                            ],
                        )
                    )

                self.assertEqual(len(writes), 6)
                self.assertEqual(len({person_id for _, person_id, _ in writes}), 6)

                # Server-side RBAC: HR Admin may create a movement, but may not
                # reverse it; Super Admin may reverse the same movement.
                hr_client = clients[2]
                super_client = clients[0]
                movement_person_id = people[6]["id"]
                movement_person = hr_client.request(
                    "GET", f"/api/personnel/{movement_person_id}"
                )
                created = hr_client.request(
                    "POST",
                    f"/api/personnel/{movement_person_id}/movements",
                    {
                        "movement_type": "unit_change",
                        "effective_date": "1405/10/01",
                        "organizational_unit": "G9 Acceptance Unit",
                        "position_code": "G9-POS-001",
                        "position_title": "G9 Acceptance Position",
                        "row_version": movement_person["row_version"],
                    },
                )
                movement_id = created["movement"]["id"]

                with self.assertRaises(ApiError):
                    hr_client.request(
                        "POST",
                        f"/api/movements/{movement_id}/reverse",
                        {"reason": "G9 forbidden HR-admin reverse"},
                    )

                reversed_result = super_client.request(
                    "POST",
                    f"/api/movements/{movement_id}/reverse",
                    {"reason": "G9 super-admin reverse"},
                )
                self.assertTrue(reversed_result["movement"]["is_reversed"])

                # Deterministic optimistic-concurrency boundary over the API:
                # both sessions hold the same row_version; only the first stale
                # snapshot may commit.
                conflict_person_id = people[7]["id"]
                first_snapshot = clients[1].request(
                    "GET", f"/api/personnel/{conflict_person_id}"
                )
                stale_snapshot = clients[3].request(
                    "GET", f"/api/personnel/{conflict_person_id}"
                )
                self.assertEqual(
                    first_snapshot["row_version"],
                    stale_snapshot["row_version"],
                )

                first_snapshot["activity_area"] = "G9-CONFLICT-WINNER"
                clients[1].request("POST", "/api/personnel", first_snapshot)

                stale_snapshot["activity_area"] = "G9-CONFLICT-STALE"
                with self.assertRaises(ApiError):
                    clients[3].request("POST", "/api/personnel", stale_snapshot)

                # Actor isolation is verified from the audit trail: each of the
                # six independent entity writes must be attributed to the
                # authenticated user that performed it.
                with contextlib.closing(sqlite3.connect(database)) as conn:
                    audit_columns = {
                        str(row[1])
                        for row in conn.execute("PRAGMA table_info(audit_log)")
                    }
                    self.assertIn("user_id", audit_columns)
                    self.assertIn("entity_type", audit_columns)
                    self.assertIn("entity_id", audit_columns)

                    actor_pairs = {
                        (str(row[0]), str(row[1]))
                        for row in conn.execute(
                            """SELECT entity_id,user_id
                               FROM audit_log
                               WHERE entity_type='personnel'"""
                        )
                    }
                    for user_id, person_id, _ in writes:
                        self.assertIn((str(person_id), str(user_id)), actor_pairs)

                    self.assertEqual(
                        conn.execute("PRAGMA integrity_check").fetchone()[0],
                        "ok",
                    )
                    self.assertEqual(
                        conn.execute("PRAGMA foreign_key_check").fetchall(),
                        [],
                    )

                self.assertTrue(repo.verify_audit_chain())
            finally:
                for client in clients:
                    try:
                        client.logout()
                    except Exception:
                        pass
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
