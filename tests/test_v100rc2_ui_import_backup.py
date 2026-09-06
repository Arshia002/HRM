from __future__ import annotations

import io
import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

from openpyxl import Workbook

from sazmanhr.backup_package import create_package, inspect_package, stage_database
from sazmanhr.database import Repository, canonical, utc_now
from sazmanhr.monthly_import import ASSIGNMENT_HEADERS, PERSONNEL_HEADERS, apply_plan, preview_xlsx

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "data" / "seed" / "sazmanhr-seed.sqlite"


def workbook_bytes(personnel_rows: list[list[object]], assignment_rows: list[list[object]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Personnel"
    ws.append(list(PERSONNEL_HEADERS))
    for row in personnel_rows:
        ws.append(row)
    wa = wb.create_sheet("Assignments")
    wa.append(list(ASSIGNMENT_HEADERS))
    for row in assignment_rows:
        wa.append(row)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


class Rc2MonthlyImportAndBackupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "hrm.sqlite"
        shutil.copy2(SEED, self.db)
        self.repo = Repository(self.db)
        self.owner = self.repo.create_user(
            "owner.rc2", "مالک آزمایش RC2", "Owner!Password2026", "owner", must_change_password=False
        )
        catalog = {
            "positions": [
                {"id": "approved-post-1", "page": 2, "title": "کارشناس آزمون RC2",
                 "parent_title": "معاونت منابع انسانی", "approved": True, "is_unit": False},
                {"id": "approved-unit-1", "page": 2, "title": "معاونت منابع انسانی",
                 "parent_title": "", "approved": True, "is_unit": True},
                {"id": "current-node-1", "page": 3, "title": "محل جاری آزمایشی",
                 "parent_title": "", "approved": False, "is_unit": True},
            ]
        }
        raw = canonical(catalog)
        with self.repo.write() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO ui_compat_datasets
                   (name,payload_json,sha256,size_bytes,record_count,imported_at)
                   VALUES(?,?,?,?,?,?)""",
                ("position-catalog", raw, "0" * 64, len(raw.encode("utf-8")), 3, utc_now()),
            )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _existing(self) -> dict:
        return self.repo.list_personnel(limit=1)["items"][0]

    def test_monthly_preview_rejects_org_change_without_assignment(self) -> None:
        person = self._existing()
        row = [""] * len(PERSONNEL_HEADERS)
        values = {
            "personnel_no": person["personnel_no"], "action": "update",
            "organizational_unit": "واحد جدید بدون حکم",
        }
        for key, value in values.items():
            row[PERSONNEL_HEADERS.index(key)] = value
        preview, _ = preview_xlsx(self.repo, workbook_bytes([row], []), "monthly.xlsx")
        self.assertFalse(preview["can_apply"])
        self.assertTrue(any("Sheet Assignments" in item for item in preview["errors"]))

    def test_approved_transfer_rejects_unit_node(self) -> None:
        person = self._existing()
        assignment = [person["personnel_no"], "approved_transfer", 2, "approved-unit-1", "حکم آزمایشی"]
        preview, _ = preview_xlsx(self.repo, workbook_bytes([], [assignment]), "monthly.xlsx")
        self.assertFalse(preview["can_apply"])
        self.assertTrue(any("یک واحد سازمانی است" in item for item in preview["errors"]))

    def test_monthly_insert_with_approved_assignment_is_atomic_and_audited(self) -> None:
        row = [""] * len(PERSONNEL_HEADERS)
        values = {
            "personnel_no": "RC2-NEW-001", "action": "insert", "full_name": "کاربر آزمایشی RC2",
            "employment_group": "رسمی", "status": "شاغل", "organizational_unit": "معاونت منابع انسانی",
        }
        for key, value in values.items():
            row[PERSONNEL_HEADERS.index(key)] = value
        assignment = ["RC2-NEW-001", "approved_transfer", 2, "approved-post-1", "حکم انتصاب آزمایشی"]
        preview, plan = preview_xlsx(self.repo, workbook_bytes([row], [assignment]), "monthly.xlsx")
        self.assertTrue(preview["can_apply"], preview["errors"])
        self.assertEqual(preview["summary"]["new_people"], 1)
        result = apply_plan(self.repo, plan, self.owner["id"], backup_filename="pre-import.sqlite")
        self.assertEqual(result["new_people"], 1)
        with self.repo.connect() as conn:
            person = conn.execute("SELECT * FROM personnel WHERE personnel_no='RC2-NEW-001'").fetchone()
            self.assertIsNotNone(person)
            self.assertEqual(person["position_title"], "کارشناس آزمون RC2")
            self.assertEqual(person["chart_node_id"], "approved-post-1")
            self.assertEqual(person["chart_page_no"], 2)
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM personnel_movements WHERE person_id=?", (person["id"],)
            ).fetchone()[0], 1)
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM import_batches WHERE id=?", (result["batch_id"],)
            ).fetchone()[0], 1)
        self.assertTrue(self.repo.verify_audit_chain())

    def test_backup_count_helper_explicitly_closes_sqlite_handle(self) -> None:
        # Windows keeps SQLite files locked if a plain sqlite3 context manager
        # exits without close(). Keep the explicit-close contract regression-safe.
        import inspect
        import sazmanhr.backup_package as backup_module

        source = inspect.getsource(backup_module._db_counts)
        self.assertIn("contextlib.closing", source)

    def test_backup_package_round_trip_and_tamper_rejection(self) -> None:
        package, meta = create_package(self.repo, self.owner["id"])
        manifest, db_raw = inspect_package(package)
        self.assertEqual(manifest["people"], 36)
        self.assertEqual(manifest["slides"], 53)
        self.assertEqual(meta["package_sha256"], __import__("hashlib").sha256(package).hexdigest())
        staged = Path(self.temp.name) / "staged.sqlite"
        checked = stage_database(package, staged)
        self.assertEqual(checked["people"], 36)
        self.assertTrue(staged.is_file())

        source = io.BytesIO(package)
        corrupted = io.BytesIO()
        with zipfile.ZipFile(source, "r") as src, zipfile.ZipFile(corrupted, "w", zipfile.ZIP_DEFLATED) as dst:
            manifest_raw = src.read("manifest.json")
            db = bytearray(src.read("database.sqlite"))
            db[-32] ^= 0x01
            dst.writestr("manifest.json", manifest_raw)
            dst.writestr("database.sqlite", bytes(db))
        with self.assertRaisesRegex(ValueError, "هش"):
            inspect_package(corrupted.getvalue())


if __name__ == "__main__":
    unittest.main()
