from __future__ import annotations

import contextlib
import hashlib
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from sazmanhr.database import Repository
from tools.real_data_migration.engine import load_directory
from tools.real_data_migration.production import CONFIRMATION, apply_to_enterprise, validate_target
from tools.real_data_migration.reconcile import reconcile, summary


def _save_book(path: Path, sheets: list[tuple[str, list[list[object]]]]) -> None:
    workbook = openpyxl.Workbook()
    workbook.remove(workbook.active)
    for title, rows in sheets:
        sheet = workbook.create_sheet(title)
        for row in rows:
            sheet.append(row)
    workbook.save(path)
    workbook.close()


def _private_fixture(root: Path):
    _save_book(root / "اکسل رسمی.xlsx", [("REPORT", [
        ["شماره پرسنلی", "نام", "نام خانوادگی", "کد ملی", "کد پست سازمانی", "کد پست سازمانی",
         "نام واحد سازمانی", "عنوان پست سازمانی", "عنوان نوع استخدام", "نام محل خدمت"],
        ["1", "علی", "رضایی", "111", "P1", "ALT1", "رسمی", "مدیر", "رسمی", "مرکز"],
        ["2", "مینا", "احمدی", "222", "P2", "ALT2", "رسمی", "کارشناس", "رسمی", "مرکز"],
    ])])
    contractor_header = [
        "شماره پرسنلی", "نام", "نام خانوادگی", "شماره ملی", "پست سازمانی",
        "شماره پست توانیر", "واحد سازمانی", "محل خدمت", "نوع استخدام",
    ]
    contractor_row = ["3", "علی", "رضایی", "111", "کارشناس", "P3", "قدیم", "غرب", "شرکتی"]
    _save_book(root / "اکسل شرکتی - حجمی - پیمانکاری.xlsx", [
        ("x", [contractor_header, contractor_row]),
        ("Sheet1", [["شماره پرسنلی", "نام", "نام خانوادگی"], ["3", "علی", "رضایی"]]),
    ])
    _save_book(root / "شهرستان.xlsx", [
        ("x", [contractor_header, contractor_row]),
        ("Sheet1", [["شماره پرسنلی", "نام", "نام خانوادگی", "واحد سازمانی"],
                    ["3", "علی", "رضایی", "ناحیه غرب"]]),
    ])
    _save_book(root / "اکسل پست با نام.xlsx", [("Sheet1", [
        ["شماره پست سازمانی", "عنوان پست", "شماره پرسنلی", "نوع پست"],
        ["P1", "مدیر", "1", "بانام ایثار"],
        ["OLD", "سابقه قدیمی", "999", "0"],
    ])])
    return reconcile(load_directory(root), expected_personnel=3)


def _target_database(path: Path) -> Repository:
    # sqlite3.Connection.__exit__ only commits/rolls back; it does not close
    # the file handle. Keep test databases replaceable/removable on Windows.
    with contextlib.closing(sqlite3.connect(path)) as conn:
        conn.execute("CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
        conn.executemany(
            "INSERT INTO metadata(key,value) VALUES(?,?)",
            (("product_id", "sazmanhr-enterprise"), ("schema_generation", "16")),
        )
        conn.commit()
    repo = Repository(path)
    for no, first, last, position, title in (
        ("1", "قدیم", "یک", "P1", "مدیر"),
        ("2", "قدیم", "دو", "P2", "کارشناس"),
        ("3", "قدیم", "سه", "P3", "کارشناس"),
    ):
        repo.save_person({
            "personnel_no": no, "first_name": first, "last_name": last,
            "full_name": f"{first} {last}", "organizational_unit": "قدیم",
            "position_code": position, "position_title": title,
        }, "test-actor")
    with repo.connect() as conn:
        conn.execute(
            """INSERT INTO chart_pages(page_no,title,approved_fixed_posts,approved_named_posts,
               approved_total_posts,extra_json,row_version,updated_at,updated_by)
               VALUES(1,'مصوب',536,32,568,'{}',1,'2026-01-01T00:00:00+00:00',NULL)"""
        )
    return repo


class EnterpriseImportV040A2Tests(unittest.TestCase):
    def test_private_workbook_profiles_are_reconciled_without_false_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            ds = _private_fixture(Path(tmp))
            result = summary(ds)
            self.assertEqual(result["persons"], 3)
            self.assertEqual(result["positions"], 1)
            self.assertEqual(result["enrichment_applied"], 1)
            self.assertEqual(result["ignored_rows"], 1)
            self.assertEqual(result["errors"], 0)
            self.assertEqual(result["warnings"], 2)
            self.assertEqual(next(p for p in ds.persons if p.personnel_no == "1").position_no, "P1")
            self.assertEqual(next(p for p in ds.persons if p.personnel_no == "3").org_unit, "ناحیه غرب")
            self.assertEqual(ds.positions[0].position_type, "بانام ایثار")
            self.assertEqual(
                {issue.code for issue in ds.issues},
                {"CROSS_SOURCE_NATIONAL_ID", "IGNORED_LEGACY_NAMED_POSITION"},
            )

    def test_target_preflight_keeps_approved_extra_page_16_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            ds = _private_fixture(source)
            database = root / "hrm.sqlite"
            _target_database(database)
            result = validate_target(
                ds, database, expected_personnel=3,
                expected_chart_fixed=536, expected_chart_named=32, expected_chart_total=568,
            )
            self.assertEqual(result["approved_total_posts"], 568)
            self.assertEqual(result["matched_named_assignments"], 1)

    def test_production_apply_is_backed_up_atomic_and_audited(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            ds = _private_fixture(source)
            database = root / "hrm.sqlite"
            _target_database(database)
            result = apply_to_enterprise(
                ds, database, root / "backups", confirmation=CONFIRMATION,
                expected_personnel=3, expected_chart_fixed=536,
                expected_chart_named=32, expected_chart_total=568,
                actor_id="test-actor",
            )
            backup = root / "backups" / str(result["backup_file"])
            self.assertTrue(backup.is_file())
            self.assertEqual(hashlib.sha256(backup.read_bytes()).hexdigest(), result["backup_sha256"])
            with contextlib.closing(sqlite3.connect(database)) as conn:
                self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM personnel").fetchone()[0], 3)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM import_batches").fetchone()[0], 1)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='production_import'").fetchone()[0], 1)
                self.assertEqual(conn.execute("SELECT organizational_unit FROM personnel WHERE personnel_no='3'").fetchone()[0], "ناحیه غرب")
                self.assertEqual(conn.execute("SELECT post_type FROM positions WHERE code='P1'").fetchone()[0], "بانام ایثار")
                self.assertEqual(conn.execute("SELECT approved_total_posts FROM chart_pages WHERE page_no=1").fetchone()[0], 568)

    def test_failed_apply_restores_verified_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            ds = _private_fixture(source)
            database = root / "hrm.sqlite"
            _target_database(database)
            with mock.patch.object(Repository, "apply_real_data_import", side_effect=RuntimeError("injected")):
                with self.assertRaisesRegex(RuntimeError, "injected"):
                    apply_to_enterprise(
                        ds, database, root / "backups", confirmation=CONFIRMATION,
                        expected_personnel=3, expected_chart_fixed=536,
                        expected_chart_named=32, expected_chart_total=568,
                    )
            backups = list((root / "backups").glob("pre-import-*.sqlite"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(hashlib.sha256(database.read_bytes()).hexdigest(), hashlib.sha256(backups[0].read_bytes()).hexdigest())
            with contextlib.closing(sqlite3.connect(database)) as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM import_batches").fetchone()[0], 0)

    def test_confirmation_is_required_before_backup_or_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            ds = _private_fixture(source)
            database = root / "hrm.sqlite"
            _target_database(database)
            with self.assertRaises(PermissionError):
                apply_to_enterprise(
                    ds, database, root / "backups", confirmation="",
                    expected_personnel=3, expected_chart_fixed=536,
                    expected_chart_named=32, expected_chart_total=568,
                )
            self.assertFalse((root / "backups").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
