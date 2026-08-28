from __future__ import annotations
import csv, json, sqlite3, subprocess, sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.real_data_migration.engine import load_directory
from tools.real_data_migration.mapping import canonical_header, header_score
from tools.real_data_migration.models import Dataset, Origin, Person, Position
from tools.real_data_migration.normalize import digits, key, text
from tools.real_data_migration.reconcile import reconcile, summary
from tools.real_data_migration.staging import create_staging_db


def test_persian_normalization():
    assert text("  علي\u200c رضا  ") == "علی رضا"
    assert digits("۱۲۳-٤٥") == "12345"
    assert key("شماره پست سازمانی") == key("شماره‌پست سازماني")


def test_aliases():
    assert canonical_header("شماره پرسنلی") == "personnel_no"
    assert canonical_header("عنوان پست") == "position_title"
    assert header_score(["شماره پرسنلی", "نام", "نام خانوادگی"]) >= 3


def _write_csv(path: Path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerows(rows)


def test_csv_load_persons(tmp_path):
    _write_csv(tmp_path / "اکسل رسمی.csv", [["شماره پرسنلی","نام","نام خانوادگی","واحد","محل خدمت"],["۱۲۳","علی","رضایی","منابع انسانی","کرمانشاه"]])
    ds = load_directory(tmp_path)
    assert len(ds.persons) == 1
    assert ds.persons[0].personnel_no == "123"
    assert ds.persons[0].org_unit == "منابع انسانی"


def test_named_positions_profile(tmp_path):
    _write_csv(tmp_path / "اکسل پست با نام.csv", [["شماره پست سازمانی","عنوان پست","شماره پرسنلی","نوع پست"],["100","مدیر","123","با نام"]])
    ds = load_directory(tmp_path)
    assert len(ds.positions) == 1
    assert ds.positions[0].position_no == "100"


def test_county_profile(tmp_path):
    _write_csv(tmp_path / "شهرستان.csv", [["نام شهرستان","کد شهرستان"],["اسلام آباد غرب","02"]])
    ds = load_directory(tmp_path)
    assert len(ds.counties) == 1


def test_duplicate_personnel_error():
    o=Origin("x","s",2)
    ds=Dataset(persons=[Person("1",origin=o),Person("1",origin=o)])
    reconcile(ds)
    assert any(i.code=="DUPLICATE_PERSONNEL_NO" for i in ds.issues)


def test_duplicate_national_id_error():
    o=Origin("x","s",2)
    ds=Dataset(persons=[Person("1",national_id="123",origin=o),Person("2",national_id="123",origin=o)])
    reconcile(ds)
    assert any(i.code=="DUPLICATE_NATIONAL_ID" for i in ds.issues)


def test_duplicate_position_error():
    o=Origin("x","s",2)
    ds=Dataset(positions=[Position("P1",origin=o),Position("P1",origin=o)])
    reconcile(ds)
    assert any(i.code=="DUPLICATE_POSITION_NO" for i in ds.issues)


def test_orphan_occupant_error():
    o=Origin("x","s",2)
    ds=Dataset(positions=[Position("P1",occupant_personnel_no="77",origin=o)])
    reconcile(ds)
    assert any(i.code=="ORPHAN_POSITION_OCCUPANT" for i in ds.issues)


def test_multiple_positions_warning():
    o=Origin("x","s",2)
    ds=Dataset(persons=[Person("1",position_no="P1",origin=o)],positions=[Position("P2",occupant_personnel_no="1",origin=o)])
    reconcile(ds)
    assert any(i.code=="PERSON_MULTIPLE_POSITIONS" and i.severity=="warning" for i in ds.issues)


def test_expected_count_mismatch():
    o=Origin("x","s",2)
    ds=Dataset(positions=[Position("P1",position_type="بانام",origin=o)])
    reconcile(ds, expected_fixed=1, expected_named=1)
    assert any(i.code=="FIXED_POSITION_COUNT_MISMATCH" for i in ds.issues)


def test_staging_refuses_errors(tmp_path):
    ds=Dataset(persons=[Person("" )])
    reconcile(ds)
    with pytest.raises(ValueError):
        create_staging_db(ds, tmp_path/"s.sqlite")


def test_staging_integrity(tmp_path):
    ds=Dataset(persons=[Person("1",first_name="علی")],positions=[Position("P1")])
    reconcile(ds)
    out=tmp_path/"s.sqlite"
    create_staging_db(ds,out)
    con=sqlite3.connect(out)
    try:
        assert con.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
        assert con.execute("select count(*) from persons").fetchone()[0]==1
    finally: con.close()


def test_no_input_files_error(tmp_path):
    ds=load_directory(tmp_path)
    assert any(i.code=="NO_INPUT_FILES" for i in ds.issues)


def test_xlsx_when_openpyxl_present(tmp_path):
    openpyxl=pytest.importorskip("openpyxl")
    wb=openpyxl.Workbook(); ws=wb.active
    ws.append(["شماره پرسنلی","نام","نام خانوادگی"]); ws.append(["9","مینا","احمدی"])
    p=tmp_path/"اکسل رسمی.xlsx"; wb.save(p)
    ds=load_directory(tmp_path)
    assert len(ds.persons)==1 and ds.persons[0].personnel_no=="9"


def test_cli_dry_run_writes_reports_not_staging(tmp_path):
    inp=tmp_path/"in"; out=tmp_path/"out"; inp.mkdir()
    _write_csv(inp/"اکسل رسمی.csv", [["شماره پرسنلی","نام","نام خانوادگی"],["1","علی","رضایی"]])
    cmd=[sys.executable,"-m","tools.real_data_migration","--input-dir",str(inp),"--output-dir",str(out)]
    r=subprocess.run(cmd,cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True)
    assert r.returncode==0, r.stderr+r.stdout
    assert (out/"migration-summary.json").exists()
    assert not (out/"staging.sqlite").exists()


def test_cli_blocks_stage_on_error(tmp_path):
    inp=tmp_path/"in"; out=tmp_path/"out"; inp.mkdir()
    _write_csv(inp/"اکسل رسمی.csv", [["نام","نام خانوادگی"],["علی","رضایی"]])
    cmd=[sys.executable,"-m","tools.real_data_migration","--input-dir",str(inp),"--output-dir",str(out),"--stage"]
    r=subprocess.run(cmd,cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True)
    assert r.returncode!=0
    assert not (out/"staging.sqlite").exists()


def test_issue_report_does_not_expose_identifier(tmp_path):
    o=Origin("x","s",2)
    ds=Dataset(persons=[Person("123456",origin=o),Person("123456",origin=o)])
    reconcile(ds)
    issue=next(i for i in ds.issues if i.code=="DUPLICATE_PERSONNEL_NO")
    assert "123456" not in issue.message
    assert "123456" not in issue.entity_ref


def test_summary_gate():
    ds=Dataset(persons=[Person("")])
    reconcile(ds)
    assert summary(ds)["eligible_for_staging"] is False

def test_gitignore_merge_is_idempotent(tmp_path):
    from ci.apply_v040a1 import merge_gitignore, BEGIN
    assert merge_gitignore(tmp_path) is True
    first=(tmp_path/'.gitignore').read_text(encoding='utf-8')
    assert 'migration/input/*' in first and BEGIN in first
    assert merge_gitignore(tmp_path) is False
    second=(tmp_path/'.gitignore').read_text(encoding='utf-8')
    assert first==second
