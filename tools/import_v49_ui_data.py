#!/usr/bin/env python3
"""Import authenticated SazmanHR v4.9 supplemental UI datasets into central SQLite.

This tool is intentionally private-deployment only. It validates the v4.9
manifest before writing and never copies source JSON into the repository tree.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from sazmanhr.compat_v49 import V49_DATASET_NAMES  # noqa: E402
from sazmanhr.database import Repository, canonical, utc_now  # noqa: E402

EXPECTED_PEOPLE = 1356
EXPECTED_SLIDES = 53


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def record_count(name: str, value: Any) -> int:
    if name == "initial-data" and isinstance(value, dict):
        return len(value.get("people") or [])
    if name == "person-education" and isinstance(value, dict):
        return len(value.get("byPersonId") or {})
    if name == "service-history" and isinstance(value, dict):
        return int((value.get("meta") or {}).get("record_count") or 0)
    if name == "training-history" and isinstance(value, dict):
        return int((value.get("meta") or {}).get("records") or 0)
    if isinstance(value, (dict, list)):
        return len(value)
    return 0


def value_for_label(items: Any, *labels: str) -> str:
    wanted = {label.strip() for label in labels}
    if not isinstance(items, list):
        return ""
    for item in items:
        if isinstance(item, dict) and str(item.get("label", "")).strip() in wanted:
            value = str(item.get("value", "") or "").strip()
            if value:
                return value
    return ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=Path)
    parser.add_argument("private_data_dir", type=Path)
    args = parser.parse_args()
    data_dir = args.private_data_dir.resolve()
    manifest_path = data_dir / "manifest.json"
    manifest_raw = manifest_path.read_bytes()
    manifest = json.loads(manifest_raw.decode("utf-8"))
    if manifest.get("version") != "4.9.0":
        raise SystemExit("Expected v4.9.0 private-data manifest.")

    loaded: dict[str, Any] = {}
    raw_meta: dict[str, tuple[str, int]] = {}
    for filename, meta in manifest.get("files", {}).items():
        name = filename.removesuffix(".json")
        if name not in V49_DATASET_NAMES:
            raise SystemExit(f"Unexpected private dataset in manifest: {filename}")
        path = data_dir / filename
        raw = path.read_bytes()
        digest = sha256_bytes(raw)
        if len(raw) != int(meta.get("bytes", -1)):
            raise SystemExit(f"Size mismatch: {filename}")
        if digest != str(meta.get("sha256", "")):
            raise SystemExit(f"SHA256 mismatch: {filename}")
        loaded[name] = json.loads(raw.decode("utf-8"))
        raw_meta[name] = (digest, len(raw))

    missing = sorted(V49_DATASET_NAMES - set(loaded))
    if missing:
        raise SystemExit(f"Missing v4.9 datasets: {missing}")
    initial = loaded["initial-data"]
    if len(initial.get("people") or []) != EXPECTED_PEOPLE or len(initial.get("slides") or []) != EXPECTED_SLIDES:
        raise SystemExit("v4.9 initial-data baseline mismatch.")
    education = loaded["person-education"].get("byPersonId") or {}
    genders = loaded["gender-map"]
    details = loaded["person-details"]
    if len(education) != EXPECTED_PEOPLE or len(genders) != EXPECTED_PEOPLE or len(details) != EXPECTED_PEOPLE:
        raise SystemExit("Supplemental 1356-person coverage check failed.")

    repo = Repository(args.database.resolve())
    now = utc_now()
    with repo.write() as conn:
        for name in sorted(loaded):
            digest, size = raw_meta[name]
            conn.execute(
                """INSERT INTO ui_compat_datasets(name,payload_json,sha256,size_bytes,record_count,imported_at)
                   VALUES(?,?,?,?,?,?)
                   ON CONFLICT(name) DO UPDATE SET payload_json=excluded.payload_json,sha256=excluded.sha256,
                     size_bytes=excluded.size_bytes,record_count=excluded.record_count,imported_at=excluded.imported_at""",
                (name, canonical(loaded[name]), digest, size, record_count(name, loaded[name]), now),
            )
        conn.execute("INSERT OR REPLACE INTO metadata(key,value) VALUES('ui_v49_reference_version','4.9.0')")
        conn.execute(
            "INSERT OR REPLACE INTO metadata(key,value) VALUES('ui_v49_private_manifest_sha256',?)",
            (sha256_bytes(manifest_raw),),
        )

        rows = conn.execute("SELECT id,gender,extra_json FROM personnel").fetchall()
        ids = {str(row["id"]) for row in rows}
        if ids != set(education) or ids != set(genders) or ids != set(details):
            raise SystemExit(
                "Normalized personnel IDs do not exactly match supplemental v4.9 person IDs "
                f"(db={len(ids)}, education={len(education)}, gender={len(genders)}, details={len(details)})."
            )
        for row in rows:
            person_id = str(row["id"])
            try:
                extra = json.loads(row["extra_json"] or "{}")
            except (TypeError, json.JSONDecodeError):
                extra = {}
            if not isinstance(extra, dict):
                extra = {}
            edu = education.get(person_id) or {}
            degree = str(edu.get("degree") or edu.get("category") or "").strip()
            if degree:
                extra["education"] = degree
                extra["education_level"] = str(edu.get("category") or degree).strip()
            birth_date = value_for_label(details.get(person_id), "تاریخ تولد")
            age = value_for_label(details.get(person_id), "سن", "سن سال")
            if birth_date:
                extra["birth_date"] = birth_date
            if age:
                extra["age"] = age
            raw_gender = str(genders.get(person_id) or "").strip().lower()
            gender = {"male": "مرد", "female": "زن", "m": "مرد", "f": "زن"}.get(raw_gender, str(row["gender"] or ""))
            conn.execute(
                "UPDATE personnel SET gender=?,extra_json=?,updated_at=? WHERE id=?",
                (gender, canonical(extra), now, person_id),
            )

    analytics = repo.analytics()
    quality = analytics.get("quality", {})
    result = {
        "version": "4.9.0",
        "dataset_count": len(loaded),
        "personnel": repo.stats()["personnel"],
        "chart_pages": analytics.get("summary", {}).get("chart_pages"),
        "quality": quality,
        "dataset_catalog": [
            {"name": name, "sha256": raw_meta[name][0], "size_bytes": raw_meta[name][1], "records": record_count(name, loaded[name])}
            for name in sorted(loaded)
        ],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["personnel"] != EXPECTED_PEOPLE or result["chart_pages"] != EXPECTED_SLIDES:
        return 2
    if any(int(quality.get(key, 0)) for key in ("missing_gender", "missing_education", "missing_age")):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
