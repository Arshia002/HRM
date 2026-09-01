from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from sazmanhr.database import Repository


PROJECT = Path(__file__).resolve().parents[1]
SEED = PROJECT / "data" / "seed" / "sazmanhr-seed.sqlite"


class V050A1AnalyticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.database = Path(self.temp.name) / "analytics.sqlite"
        shutil.copy2(SEED, self.database)
        self.repo = Repository(self.database)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_aggregate_dashboards_never_return_personnel_records(self) -> None:
        with self.repo.write() as conn:
            people = conn.execute("SELECT id FROM personnel ORDER BY personnel_no LIMIT 2").fetchall()
            conn.execute(
                "UPDATE personnel SET extra_json=? WHERE id=?",
                (json.dumps({"education_level": "کارشناسی", "birth_year": "1365"}), people[0][0]),
            )
            conn.execute(
                "UPDATE personnel SET extra_json=? WHERE id=?",
                (json.dumps({"degree": "کارشناسی ارشد", "age": 42}), people[1][0]),
            )

        result = self.repo.analytics()
        self.assertEqual(result["summary"]["personnel"], 36)
        self.assertEqual(result["summary"]["chart_pages"], 53)
        self.assertEqual(result["summary"]["approved_chart_total"], 0)
        self.assertEqual(sum(item["count"] for item in result["distributions"]["education"]), 2)
        self.assertEqual(sum(item["count"] for item in result["distributions"]["age"]), 2)
        self.assertEqual(result["quality"]["missing_education"], 34)
        self.assertEqual(result["quality"]["missing_age"], 34)

        serialized = json.dumps(result, ensure_ascii=False).lower()
        for forbidden in ("personnel_no", "full_name", "national_id", "extra_json"):
            self.assertNotIn(forbidden, serialized)

    def test_migration_status_distinguishes_demo_from_enterprise_target(self) -> None:
        status = self.repo.migration_status()
        self.assertEqual(status["personnel"], 36)
        self.assertEqual(status["chart"]["total"], 0)
        self.assertFalse(status["enterprise_target_ready"])
        self.assertEqual(status["expected"], {
            "personnel": 1356, "fixed": 536, "named": 32, "total": 568,
        })

    def test_user_listing_includes_effective_access_without_secrets(self) -> None:
        owner = self.repo.create_user(
            "ui.owner", "مدیر رابط", "Strong!Password1405", "owner", must_change_password=False,
        )
        editor = self.repo.create_user(
            "ui.editor", "کاربر رابط", "Strong!Password1406", "editor",
            actor_id=owner["id"], must_change_password=False,
        )
        self.repo.set_user_permissions(editor["id"], {"view_audit": "allow", "edit_chart": "deny"}, owner["id"])
        with self.assertRaisesRegex(ValueError, "مالک اصلی"):
            self.repo.set_user_permissions(owner["id"], {"manage_users": "deny"}, owner["id"])

        listed = {item["id"]: item for item in self.repo.list_users()}
        self.assertIn("view_audit", listed[editor["id"]]["permissions"])
        self.assertNotIn("edit_chart", listed[editor["id"]]["permissions"])
        self.assertEqual(listed[editor["id"]]["permission_overrides"], {
            "edit_chart": "deny", "view_audit": "allow",
        })
        for item in listed.values():
            self.assertNotIn("password_hash", item)


if __name__ == "__main__":
    unittest.main()
