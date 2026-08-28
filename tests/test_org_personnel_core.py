from __future__ import annotations

import tempfile
import unittest
import shutil
from pathlib import Path

from sazmanhr.database import ConflictError, Repository


class OrganizationPersonnelCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "hrm.sqlite"
        seed = Path(__file__).resolve().parents[1] / "data" / "seed" / "sazmanhr-seed.sqlite"
        shutil.copy2(seed, self.db)
        self.repo = Repository(self.db)
        self.owner = self.repo.create_user(
            "owner", "مدیر آزمون", "Owner!Password1500", "owner", must_change_password=False
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _payload(self, no: str = "D-1001") -> dict:
        return {
            "personnel_no": no,
            "first_name": "کاربر",
            "last_name": "آزمایشی",
            "full_name": "کاربر آزمایشی",
            "organizational_unit": "معاونت منابع انسانی",
            "position_code": "P-DEMO-001",
            "position_title": "کارشناس منابع انسانی",
            "employment_group": "رسمی",
            "status": "فعال",
            "actual_location": "ستاد",
            "company": "Demo",
        }

    def test_person_save_builds_unit_position_and_assignment_projection(self):
        before = self.repo.organization_summary()
        person = self.repo.save_person(self._payload(), self.owner["id"])
        self.assertEqual(person["personnel_no"], "D-1001")
        self.assertIsNotNone(person["assignment"])
        self.assertEqual(person["assignment"]["unit_title"], "معاونت منابع انسانی")
        self.assertEqual(person["assignment"]["normalized_position_code"], "P-DEMO-001")

        summary = self.repo.organization_summary()
        self.assertGreaterEqual(summary["units"], before["units"])
        self.assertEqual(summary["positions"], before["positions"] + 1)
        self.assertEqual(summary["occupied_positions"], before["occupied_positions"] + 1)

    def test_personnel_search_and_facets(self):
        self.repo.save_person(self._payload("D-1001"), self.owner["id"])
        second = self._payload("D-1002")
        second.update({
            "full_name": "نیروی دوم",
            "first_name": "نیروی",
            "last_name": "دوم",
            "organizational_unit": "امور کارکنان و رفاه",
            "position_code": "P-DEMO-002",
            "position_title": "کارشناس رفاه",
            "employment_group": "شرکتی",
            "actual_location": "کرمانشاه",
        })
        self.repo.save_person(second, self.owner["id"])

        result = self.repo.list_personnel(query="رفاه")
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["personnel_no"], "D-1002")
        self.assertIn("رسمی", result["facets"]["employment"])
        self.assertIn("شرکتی", result["facets"]["employment"])

    def test_positions_occupancy_filter(self):
        before_occupied = self.repo.list_positions(occupancy="occupied")["total"]
        person = self.repo.save_person(self._payload(), self.owner["id"])
        occupied = self.repo.list_positions(occupancy="occupied")
        self.assertEqual(occupied["total"], before_occupied + 1)
        created = next(item for item in occupied["items"] if item["code"] == "P-DEMO-001")
        self.assertEqual(created["occupant_name"], person["full_name"])

    def test_update_conflict_is_rejected_and_audited(self):
        person = self.repo.save_person(self._payload(), self.owner["id"])
        stale = dict(person)
        person["status"] = "ماموریت"
        updated = self.repo.save_person(person, self.owner["id"])
        self.assertEqual(updated["row_version"], 2)
        stale["status"] = "مرخصی"
        with self.assertRaises(ConflictError):
            self.repo.save_person(stale, self.owner["id"])
        self.assertTrue(self.repo.verify_audit_chain())

    def test_unassigned_count_changes_when_position_is_removed(self):
        before = self.repo.stats()["unassigned"]
        person = self.repo.save_person(self._payload(), self.owner["id"])
        self.assertEqual(self.repo.stats()["unassigned"], before)
        person["position_code"] = ""
        person["position_title"] = ""
        self.repo.save_person(person, self.owner["id"])
        self.assertEqual(self.repo.stats()["unassigned"], before + 1)


if __name__ == "__main__":
    unittest.main()
