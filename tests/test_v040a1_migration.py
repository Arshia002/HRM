from __future__ import annotations
import csv
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.real_data_migration.engine import load_directory
from tools.real_data_migration.mapping import canonical_header, header_score
from tools.real_data_migration.models import Dataset, Origin, Person, Position
from tools.real_data_migration.normalize import digits, key, text
from tools.real_data_migration.reconcile import reconcile, summary
from tools.real_data_migration.staging import create_staging_db

try:
    import openpyxl  # type: ignore
except ImportError:
    openpyxl = None


def _write_csv(path: Path, rows) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        csv.writer(handle).writerows(rows)


class MigrationV040A1Tests(unittest.TestCase):
    def test_persian_normalization(self):
        self.assertEqual(text("  علي\u200c رضا  "), "علی رضا")
        self.assertEqual(digits("۱۲۳-٤٥"), "12345")
        self.assertEqual(key("شماره پست سازمانی"), key("شماره‌پست سازماني"))

    def test_aliases(self):
        self.assertEqual(canonical_header("شماره پرسنلی"), "personnel_no")
        self.assertEqual(canonical_header("عنوان پست"), "position_title")
        self.assertGreaterEqual(header_score(["شماره پرسنلی", "نام", "نام خانوادگی"]), 3)

    def test_csv_load_persons(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_csv(root / "اکسل رسمی.csv", [["شماره پرسنلی","نام","نام خانوادگی","واحد","محل خدمت"],["۱۲۳","علی","رضایی","منابع انسانی","کرمانشاه"]])
            ds = load_directory(root)
            self.assertEqual(len(ds.persons), 1)
            self.assertEqual(ds.persons[0].personnel_no, "123")
            self.assertEqual(ds.persons[0].org_unit, "منابع انسانی")

    def test_named_positions_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_csv(root / "اکسل پست با نام.csv", [["شماره پست سازمانی","عنوان پست","شماره پرسنلی","نوع پست"],["100","مدیر","123","با نام"]])
            ds = load_directory(root)
            self.assertEqual(len(ds.positions), 1)
            self.assertEqual(ds.positions[0].position_no, "100")

    def test_county_workbook_enriches_existing_person(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_csv(root / "اکسل رسمی.csv", [["شماره پرسنلی","نام","نام خانوادگی"],["1","علی","رضایی"]])
            _write_csv(root / "شهرستان.csv", [["شماره پرسنلی","واحد سازمانی"],["1","ناحیه غرب"]])
            ds = load_directory(root)
            self.assertEqual(len(ds.counties), 0)
            self.assertEqual(ds.persons[0].org_unit, "ناحیه غرب")
            self.assertEqual(ds.enrichment_applied, 1)

    def test_duplicate_personnel_error(self):
        origin = Origin("x", "s", 2)
        ds = Dataset(persons=[Person("1", origin=origin), Person("1", origin=origin)])
        reconcile(ds)
        self.assertTrue(any(i.code == "DUPLICATE_PERSONNEL_NO" for i in ds.issues))

    def test_duplicate_national_id_error(self):
        origin = Origin("x", "s", 2)
        ds = Dataset(persons=[Person("1", national_id="123", origin=origin), Person("2", national_id="123", origin=origin)])
        reconcile(ds)
        self.assertTrue(any(i.code == "DUPLICATE_NATIONAL_ID" for i in ds.issues))

    def test_duplicate_position_error(self):
        origin = Origin("x", "s", 2)
        ds = Dataset(positions=[Position("P1", origin=origin), Position("P1", origin=origin)])
        reconcile(ds)
        self.assertTrue(any(i.code == "DUPLICATE_POSITION_NO" for i in ds.issues))

    def test_orphan_occupant_error(self):
        origin = Origin("x", "s", 2)
        ds = Dataset(positions=[Position("P1", occupant_personnel_no="77", origin=origin)])
        reconcile(ds)
        self.assertTrue(any(i.code == "ORPHAN_POSITION_OCCUPANT" for i in ds.issues))

    def test_multiple_positions_warning(self):
        origin = Origin("x", "s", 2)
        ds = Dataset(persons=[Person("1", position_no="P1", origin=origin)], positions=[Position("P2", occupant_personnel_no="1", origin=origin)])
        reconcile(ds)
        self.assertTrue(any(i.code == "PERSON_MULTIPLE_POSITIONS" and i.severity == "warning" for i in ds.issues))

    def test_expected_count_mismatch(self):
        origin = Origin("x", "s", 2)
        ds = Dataset(positions=[Position("P1", position_type="بانام", origin=origin)])
        reconcile(ds, expected_fixed=1, expected_named=1)
        self.assertTrue(any(i.code == "FIXED_POSITION_COUNT_MISMATCH" for i in ds.issues))

    def test_staging_refuses_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            ds = Dataset(persons=[Person("")])
            reconcile(ds)
            with self.assertRaises(ValueError):
                create_staging_db(ds, Path(tmp) / "s.sqlite")

    def test_staging_integrity(self):
        with tempfile.TemporaryDirectory() as tmp:
            ds = Dataset(persons=[Person("1", first_name="علی")], positions=[Position("P1")])
            reconcile(ds)
            out = Path(tmp) / "s.sqlite"
            create_staging_db(ds, out)
            conn = sqlite3.connect(out)
            try:
                self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertEqual(conn.execute("select count(*) from persons").fetchone()[0], 1)
            finally:
                conn.close()

    def test_no_input_files_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            ds = load_directory(Path(tmp))
            self.assertTrue(any(i.code == "NO_INPUT_FILES" for i in ds.issues))

    @unittest.skipIf(openpyxl is None, "openpyxl is optional in the CI source gate")
    def test_xlsx_when_openpyxl_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workbook = openpyxl.Workbook()
            sheet = workbook.active
            sheet.append(["شماره پرسنلی", "نام", "نام خانوادگی"])
            sheet.append(["9", "مینا", "احمدی"])
            path = root / "اکسل رسمی.xlsx"
            workbook.save(path)
            workbook.close()
            ds = load_directory(root)
            self.assertEqual(len(ds.persons), 1)
            self.assertEqual(ds.persons[0].personnel_no, "9")

    def test_cli_dry_run_writes_reports_not_staging(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inp = root / "in"
            out = root / "out"
            inp.mkdir()
            _write_csv(inp / "اکسل رسمی.csv", [["شماره پرسنلی","نام","نام خانوادگی"],["1","علی","رضایی"]])
            cmd = [sys.executable, "-m", "tools.real_data_migration", "--input-dir", str(inp), "--output-dir", str(out)]
            result = subprocess.run(cmd, cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertTrue((out / "migration-summary.json").exists())
            self.assertFalse((out / "staging.sqlite").exists())

    def test_cli_blocks_stage_on_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inp = root / "in"
            out = root / "out"
            inp.mkdir()
            _write_csv(inp / "اکسل رسمی.csv", [["نام","نام خانوادگی"],["علی","رضایی"]])
            cmd = [sys.executable, "-m", "tools.real_data_migration", "--input-dir", str(inp), "--output-dir", str(out), "--stage"]
            result = subprocess.run(cmd, cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((out / "staging.sqlite").exists())

    def test_issue_report_does_not_expose_identifier(self):
        origin = Origin("x", "s", 2)
        ds = Dataset(persons=[Person("123456", origin=origin), Person("123456", origin=origin)])
        reconcile(ds)
        issue = next(i for i in ds.issues if i.code == "DUPLICATE_PERSONNEL_NO")
        self.assertNotIn("123456", issue.message)
        self.assertNotIn("123456", issue.entity_ref)

    def test_summary_gate(self):
        ds = Dataset(persons=[Person("")])
        reconcile(ds)
        self.assertFalse(summary(ds)["eligible_for_staging"])

    def test_gitignore_merge_is_idempotent(self):
        from ci.apply_v040a1 import BEGIN, merge_gitignore
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertTrue(merge_gitignore(root))
            first = (root / ".gitignore").read_text(encoding="utf-8")
            self.assertIn("migration/input/*", first)
            self.assertIn(BEGIN, first)
            self.assertFalse(merge_gitignore(root))
            second = (root / ".gitignore").read_text(encoding="utf-8")
            self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main(verbosity=2)
