from __future__ import annotations
import sqlite3
from pathlib import Path
from .models import Dataset

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE persons(
  personnel_no TEXT PRIMARY KEY,
  first_name TEXT, last_name TEXT, national_id TEXT,
  employment_type TEXT, org_unit TEXT, location TEXT,
  position_no TEXT, position_title TEXT
);
CREATE TABLE positions(
  position_no TEXT PRIMARY KEY,
  title TEXT, org_unit TEXT, location TEXT, position_type TEXT,
  occupant_personnel_no TEXT
);
CREATE TABLE counties(name TEXT PRIMARY KEY, code TEXT);
"""


def create_staging_db(ds: Dataset, path: Path) -> None:
    if any(i.severity == "error" for i in ds.issues):
        raise ValueError("Refusing staging because reconciliation has errors.")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    if tmp.exists():
        tmp.unlink()
    con = sqlite3.connect(tmp)
    try:
        con.executescript(SCHEMA)
        con.execute("INSERT INTO meta VALUES (?,?)", ("schema", "hrm-v0.5.0-alpha.1-staging"))
        con.executemany("INSERT INTO persons VALUES (?,?,?,?,?,?,?,?,?)", [
            (p.personnel_no,p.first_name,p.last_name,p.national_id,p.employment_type,p.org_unit,p.location,p.position_no,p.position_title)
            for p in ds.persons
        ])
        con.executemany("INSERT INTO positions VALUES (?,?,?,?,?,?)", [
            (p.position_no,p.title,p.org_unit,p.location,p.position_type,p.occupant_personnel_no)
            for p in ds.positions
        ])
        con.executemany("INSERT OR IGNORE INTO counties VALUES (?,?)", [(c.name,c.code) for c in ds.counties])
        ok = con.execute("PRAGMA integrity_check").fetchone()[0]
        if ok != "ok":
            raise RuntimeError(f"SQLite integrity_check failed: {ok}")
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    tmp.replace(path)
