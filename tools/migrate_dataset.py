#!/usr/bin/env python3
"""Import only personnel and organization-chart data into the clean schema.

Accounts, sessions, logs, runtime metadata and executable content are never
copied. The output is a normalized seed database plus portable gzip exports.
"""

from __future__ import annotations

import argparse
import contextlib
import gzip
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from sazmanhr.config import PRODUCT_ID, SCHEMA_GENERATION  # noqa: E402
from sazmanhr.database import Repository, canonical, utc_now  # noqa: E402

PERSON_FIELDS = {
    "id", "personnel_no", "name", "last_name", "full_name", "gender", "organizational_unit",
    "position_code", "position_title", "employment_group", "employment_subtype", "status",
    "activity_area", "actual_location", "company",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_payload(source: Path) -> dict:
    conn = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"Source integrity check failed: {integrity}")
        row = conn.execute("SELECT bootstrap_json FROM app_state LIMIT 1").fetchone()
        if not row:
            raise RuntimeError("Source dataset does not contain bootstrap data.")
        payload = json.loads(row[0])
    finally:
        conn.close()
    if not isinstance(payload.get("people"), list) or not isinstance(payload.get("slides"), list):
        raise RuntimeError("Personnel or chart collection is missing.")
    return payload


def write_gzip_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", compresslevel=9) as handle:
        json.dump(value, handle, ensure_ascii=False, separators=(",", ":"))


def migrate(source: Path, output_root: Path) -> dict:
    payload = load_payload(source)
    people = payload["people"]
    slides = payload["slides"]
    if len(people) != 1356:
        raise RuntimeError(f"Expected 1356 personnel records, received {len(people)}.")
    seed_dir = output_root / "seed"
    export_dir = output_root / "export"
    seed_dir.mkdir(parents=True, exist_ok=True)
    target = seed_dir / "sazmanhr-seed.sqlite"
    target.unlink(missing_ok=True)
    with contextlib.closing(sqlite3.connect(target)) as bootstrap:
        bootstrap.execute("CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        bootstrap.executemany(
            "INSERT INTO metadata(key,value) VALUES(?,?)",
            (("product_id", PRODUCT_ID), ("schema_generation", SCHEMA_GENERATION)),
        )
        bootstrap.commit()
    repo = Repository(target)
    now = utc_now()
    seen_personnel_numbers: set[str] = set()
    with repo.write() as conn:
        for index, source_person in enumerate(people):
            person = dict(source_person)
            person_id = str(person.get("id") or f"person-{index + 1}")
            personnel_no = str(person.get("personnel_no") or "").strip()
            if not personnel_no or personnel_no in seen_personnel_numbers:
                raise RuntimeError(f"Invalid or duplicate personnel number at item {index + 1}.")
            seen_personnel_numbers.add(personnel_no)
            values = (
                person_id, personnel_no, str(person.get("name", "")).strip(),
                str(person.get("last_name", "")).strip(), str(person.get("full_name", "")).strip(),
                str(person.get("gender", "")).strip(), str(person.get("organizational_unit", "")).strip(),
                str(person.get("position_code", "")).strip(), str(person.get("position_title", "")).strip(),
                str(person.get("employment_group", "")).strip(), str(person.get("employment_subtype", "")).strip(),
                str(person.get("status", "")).strip(), str(person.get("activity_area", "")).strip(),
                str(person.get("actual_location", "")).strip(), str(person.get("company", "")).strip(),
                int(person.get("current_chart_page_v421") or person.get("home_page") or 0) or None,
                str(person.get("approved_node_id") or person.get("target_node_id") or "").strip(),
                canonical({key: value for key, value in person.items() if key not in PERSON_FIELDS}), 1, now, None,
            )
            conn.execute(
                """INSERT INTO personnel(id,personnel_no,first_name,last_name,full_name,gender,
                organizational_unit,position_code,position_title,employment_group,employment_subtype,status,
                activity_area,actual_location,company,chart_page_no,chart_node_id,extra_json,row_version,updated_at,updated_by)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                values,
            )
        for slide_index, source_slide in enumerate(slides):
            slide = dict(source_slide)
            page_no = int(slide.get("page") or slide_index + 1)
            nodes = slide.pop("nodes", [])
            lines = slide.pop("lines", [])
            title = str(slide.pop("title", f"صفحه {page_no}"))
            fixed = slide.pop("approved_fixed_posts", None)
            named = slide.pop("approved_named_posts", None)
            total = slide.pop("approved_total_posts", None)
            conn.execute(
                """INSERT INTO chart_pages(page_no,title,approved_fixed_posts,approved_named_posts,
                approved_total_posts,extra_json,row_version,updated_at,updated_by) VALUES(?,?,?,?,?,?,?,?,?)""",
                (page_no, title, fixed, named, total, canonical(slide), 1, now, None),
            )
            for node_index, node in enumerate(nodes):
                node_id = str(node.get("id") or f"p{page_no}-node-{node_index + 1}")
                conn.execute(
                    "INSERT INTO chart_nodes(id,page_no,node_json,row_version,updated_at,updated_by) VALUES(?,?,?,?,?,?)",
                    (node_id, page_no, canonical(node), 1, now, None),
                )
            for line_index, line in enumerate(lines):
                line_id = str(line.get("id") or f"p{page_no}-line-{line_index + 1}")
                conn.execute(
                    "INSERT INTO chart_lines(id,page_no,line_json,row_version,updated_at,updated_by) VALUES(?,?,?,?,?,?)",
                    (line_id, page_no, canonical(line), 1, now, None),
                )
        default_widgets = (
            ("welcome", "پیام سازمانی", "text", {"text": "سامانه یکپارچه منابع انسانی و چارت سازمانی"}, 1),
            ("help", "راهنمای مدیر", "text", {"text": "همه تغییرات ثبت و برای مدیران متصل همگام می‌شود."}, 2),
        )
        for widget_id, title, widget_type, config, position in default_widgets:
            conn.execute(
                """INSERT INTO dashboard_widgets(id,title,widget_type,config_json,position,is_enabled,row_version,updated_at,updated_by)
                VALUES(?,?,?,?,?,1,1,?,NULL)""",
                (widget_id, title, widget_type, canonical(config), position, now),
            )
        conn.execute("INSERT OR REPLACE INTO metadata(key,value) VALUES('dataset_version','1500')")
        conn.execute("INSERT OR REPLACE INTO metadata(key,value) VALUES('dataset_personnel_count','1356')")
        conn.execute("INSERT OR REPLACE INTO metadata(key,value) VALUES('dataset_chart_pages',?)", (str(len(slides)),))
    with repo.connect() as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Generated database failed integrity check.")
        counts = {
            "personnel": conn.execute("SELECT COUNT(*) FROM personnel").fetchone()[0],
            "chart_pages": conn.execute("SELECT COUNT(*) FROM chart_pages").fetchone()[0],
            "chart_nodes": conn.execute("SELECT COUNT(*) FROM chart_nodes").fetchone()[0],
            "chart_lines": conn.execute("SELECT COUNT(*) FROM chart_lines").fetchone()[0],
            "users": conn.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        }
    write_gzip_json(export_dir / "personnel.json.gz", people)
    write_gzip_json(export_dir / "organization-chart.json.gz", slides)
    manifest = {
        "format": "HRM clean seed",
        "schema_version": 5,
        "dataset_version": 1500,
        "generated_at": now,
        "counts": counts,
        "source_sha256": sha256(source),
        "database_sha256": sha256(target),
        "contains_accounts": False,
        "contains_sessions": False,
        "migration_policy": "data-only: personnel and organization chart",
    }
    (seed_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    manifest = migrate(args.source.resolve(), args.output.resolve())
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
