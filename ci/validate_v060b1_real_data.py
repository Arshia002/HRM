#!/usr/bin/env python3
"""Protected HRM v0.6 real-data validation with aggregate-only evidence."""

from __future__ import annotations

import argparse
import collections
import contextlib
import hashlib
import json
import shutil
import sqlite3
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT, ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ci.real_data_bundle import BundleError, decrypt_bundle, key_from_environment  # noqa: E402
from sazmanhr.database import Repository, utc_now  # noqa: E402
from tools.real_data_migration.engine import load_directory  # noqa: E402
from tools.real_data_migration.production import (  # noqa: E402
    CONFIRMATION,
    apply_to_enterprise,
    restore_verified_backup,
    sha256_file,
)
from tools.real_data_migration.reconcile import reconcile, summary  # noqa: E402
from tools.real_data_migration.staging import create_staging_db  # noqa: E402


@dataclass(frozen=True)
class RealDataContract:
    personnel: int = 1356
    county_enrichments: int = 590
    active_named_positions: int = 185
    ignored_legacy_type_zero: int = 1
    fixed: int = 536
    named: int = 32
    total: int = 568
    page_16_total: int = 24


class RealDataValidationError(RuntimeError):
    pass


def official_contract() -> RealDataContract:
    metadata = json.loads((ROOT / "VERSION-V060B1.json").read_text(encoding="utf-8"))
    chart = metadata.get("approved_chart", {})
    assignments = metadata.get("expected_source_assignments", {})
    values = {
        "personnel": metadata.get("expected_personnel"),
        "county_enrichments": assignments.get("county_enrichments"),
        "active_named_positions": assignments.get("active_named_positions"),
        "ignored_legacy_type_zero": assignments.get("ignored_legacy_type_zero"),
        "fixed": chart.get("fixed"),
        "named": chart.get("named"),
        "total": chart.get("total"),
        "page_16_total": chart.get("page_16_total"),
    }
    expected = {
        "personnel": 1356, "county_enrichments": 590,
        "active_named_positions": 185, "ignored_legacy_type_zero": 1,
        "fixed": 536, "named": 32,
        "total": 568, "page_16_total": 24,
    }
    if values != expected:
        raise RealDataValidationError(f"Version metadata real-data contract drifted: {values!r}")
    return RealDataContract(**expected)


def _shadow_person_id(personnel_no: str) -> str:
    return "pilot-person-" + hashlib.sha256(personnel_no.encode("utf-8")).hexdigest()[:20]


def prepare_shadow_target(dataset, target: Path, contract: RealDataContract) -> None:
    """Create an ephemeral production-shaped target without exporting PII."""
    shutil.copy2(ROOT / "data" / "seed" / "sazmanhr-seed.sqlite", target)
    repo = Repository(target)
    now = utc_now()
    with repo.write() as conn:
        for table in ("personnel_assignments", "positions", "organizational_units", "personnel"):
            conn.execute(f"DELETE FROM {table}")
        conn.execute("DELETE FROM import_batches")
        conn.execute("DELETE FROM audit_log")
        conn.execute("DELETE FROM change_feed")
        conn.execute(
            """UPDATE chart_pages SET approved_fixed_posts=?,approved_named_posts=?,
               approved_total_posts=? WHERE page_no=1""",
            (contract.fixed, contract.named, contract.total),
        )
        conn.execute(
            "UPDATE chart_pages SET approved_total_posts=? WHERE page_no=16",
            (contract.page_16_total,),
        )
        conn.execute("INSERT OR REPLACE INTO metadata(key,value) VALUES('dataset_kind','pilot-shadow')")
        for index, person in enumerate(dataset.persons, start=1):
            conn.execute(
                """INSERT INTO personnel(
                   id,personnel_no,first_name,last_name,full_name,gender,organizational_unit,
                   position_code,position_title,employment_group,employment_subtype,status,
                   activity_area,actual_location,company,chart_page_no,chart_node_id,extra_json,
                   row_version,updated_at,updated_by)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    _shadow_person_id(person.personnel_no), person.personnel_no,
                    "", "", f"pilot-shadow-{index}", "", "", person.position_no,
                    person.position_title, "", "", "", "", "", "", None,
                    "", "{}", 1, now, None,
                ),
            )
    repo.initialize()


def projection_digest(database: Path) -> str:
    with contextlib.closing(sqlite3.connect(database)) as conn:
        payload = {
            "personnel": list(conn.execute(
                """SELECT personnel_no,first_name,last_name,organizational_unit,position_code,
                   position_title,employment_group,actual_location FROM personnel ORDER BY personnel_no"""
            )),
            "positions": list(conn.execute("SELECT code,post_type,status FROM positions ORDER BY code")),
            "assignments": list(conn.execute(
                """SELECT pe.personnel_no,p.code,a.is_primary,a.end_date
                   FROM personnel_assignments a
                   JOIN personnel pe ON pe.id=a.person_id
                   JOIN positions p ON p.id=a.position_id
                   ORDER BY pe.personnel_no,p.code"""
            )),
        }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _staging_counts(path: Path) -> dict[str, int | str]:
    with contextlib.closing(sqlite3.connect(path)) as conn:
        return {
            "integrity": str(conn.execute("PRAGMA integrity_check").fetchone()[0]),
            "personnel": int(conn.execute("SELECT COUNT(*) FROM persons").fetchone()[0]),
            "positions": int(conn.execute("SELECT COUNT(*) FROM positions").fetchone()[0]),
        }


def validate_real_data(bundle: Path, key: bytes, output: Path, contract: RealDataContract) -> dict[str, object]:
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="hrm-v060b1-real-data-") as temp_name:
        temp = Path(temp_name)
        input_dir = temp / "decrypted-input"
        envelope = decrypt_bundle(bundle, key, input_dir)
        dataset = reconcile(
            load_directory(input_dir),
            expected_personnel=contract.personnel,
        )
        dataset_summary = summary(dataset)
        issue_counts = collections.Counter(issue.code for issue in dataset.issues)
        error_codes = sorted({issue.code for issue in dataset.issues if issue.severity == "error"})
        if error_codes:
            raise RealDataValidationError(
                "Real-data reconciliation failed with protected issue codes: " + ", ".join(error_codes)
            )

        # Source workbook assignments and approved chart capacity are distinct
        # domains.  The named-position workbook contains 185 active occupant
        # assignments (plus one retired type-0 row); the Enterprise chart page
        # independently remains 536 fixed + 32 named = 568 approved posts.
        source_aggregates = {
            "personnel": dataset_summary["persons"],
            "county_enrichments": dataset_summary["enrichment_applied"],
            "active_named_positions": dataset_summary["positions"],
            "ignored_legacy_type_zero": dataset_summary["ignored_rows"],
        }
        expected_source_aggregates = {
            "personnel": contract.personnel,
            "county_enrichments": contract.county_enrichments,
            "active_named_positions": contract.active_named_positions,
            "ignored_legacy_type_zero": contract.ignored_legacy_type_zero,
        }
        if source_aggregates != expected_source_aggregates:
            raise RealDataValidationError(
                "Private-source aggregate contract failed: "
                f"observed={source_aggregates!r}, expected={expected_source_aggregates!r}"
            )

        staging = temp / "staging.sqlite"
        create_staging_db(dataset, staging)
        staging_result = _staging_counts(staging)
        expected_staging = {
            "integrity": "ok", "personnel": contract.personnel,
            "positions": contract.active_named_positions,
        }
        if staging_result != expected_staging:
            raise RealDataValidationError(f"Private staging aggregate contract failed: {staging_result!r}")

        target = temp / "pilot-shadow.sqlite"
        prepare_shadow_target(dataset, target, contract)
        first_backups = temp / "backups-first"
        first = apply_to_enterprise(
            dataset, target, first_backups, confirmation=CONFIRMATION,
            expected_personnel=contract.personnel, expected_chart_fixed=contract.fixed,
            expected_chart_named=contract.named, expected_chart_total=contract.total,
            expected_page_16_total=contract.page_16_total,
        )
        first_digest = projection_digest(target)
        first_backup = first_backups / str(first["backup_file"])
        restore_verified_backup(target, first_backup, str(first["backup_sha256"]))
        if sha256_file(target) != str(first["backup_sha256"]):
            raise RealDataValidationError("Verified rollback did not restore the backup byte-for-byte.")

        replay = apply_to_enterprise(
            dataset, target, temp / "backups-replay", confirmation=CONFIRMATION,
            expected_personnel=contract.personnel, expected_chart_fixed=contract.fixed,
            expected_chart_named=contract.named, expected_chart_total=contract.total,
            expected_page_16_total=contract.page_16_total,
        )
        replay_digest = projection_digest(target)
        if replay_digest != first_digest:
            raise RealDataValidationError("Real-data replay produced a different logical projection digest.")

        with contextlib.closing(sqlite3.connect(target)) as conn:
            final_integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
            import_batches = int(conn.execute("SELECT COUNT(*) FROM import_batches").fetchone()[0])
        if final_integrity != "ok" or import_batches != 1:
            raise RealDataValidationError("Post-replay database integrity/audit batch contract failed.")

        result: dict[str, object] = {
            "summary_schema": 1,
            "product": "HRM",
            "version": "0.7.0-rc.1",
            "status": "pass",
            "privacy": {"aggregate_only": True, "raw_identifiers": False, "plaintext_artifact": False},
            "provenance": envelope,
            "approved_contract": {
                "personnel": contract.personnel, "fixed_posts": contract.fixed,
                "named_posts": contract.named, "total_posts": contract.total,
                "page_16_total": contract.page_16_total,
            },
            "source_contract": {
                "county_enrichments": contract.county_enrichments,
                "active_named_positions": contract.active_named_positions,
                "ignored_legacy_type_zero": contract.ignored_legacy_type_zero,
            },
            "reconciliation": {**dataset_summary, "issue_codes": dict(sorted(issue_counts.items()))},
            "staging": staging_result,
            "production_shadow": {
                "first_updated_personnel": first["updated_personnel"],
                "replay_updated_personnel": replay["updated_personnel"],
                "named_position_assignments": replay["named_position_assignments"],
                "rollback_verified": True,
                "replay_verified": True,
                "projection_sha256": replay_digest,
                "database_integrity": final_integrity,
                "audit_batches": import_batches,
                "preflight": replay["preflight"],
                "postflight": replay["postflight"],
            },
        }
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--key-env", default="HRM_REAL_DATA_KEY")
    args = parser.parse_args()
    try:
        result = validate_real_data(args.bundle, key_from_environment(args.key_env), args.output, official_contract())
    except (BundleError, RealDataValidationError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # Do not echo parser/database values into CI logs.
        print(
            f"FAIL: protected real-data validation stopped safely ({type(exc).__name__}).",
            file=sys.stderr,
        )
        return 1
    production = result["production_shadow"]
    print(json.dumps({
        "status": result["status"], "version": result["version"],
        "approved_contract": result["approved_contract"],
        "source_contract": result["source_contract"],
        "rollback_verified": production["rollback_verified"],
        "replay_verified": production["replay_verified"],
    }, ensure_ascii=False))
    print("PASS: protected HRM v0.6 real-data validation completed with aggregate-only evidence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
