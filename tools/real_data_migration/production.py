from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from sazmanhr.config import validate_database_identity  # noqa: E402
from sazmanhr.database import Repository  # noqa: E402
from sazmanhr.operations import sqlite_integrity  # noqa: E402

from .models import Dataset, Issue  # noqa: E402
from .reconcile import summary  # noqa: E402


CONFIRMATION = "APPLY-TO-HRM"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_digest(ds: Dataset) -> str:
    payload = {
        "files": sorted(ds.source_files),
        "persons": sorted(
            (
                person.personnel_no, person.first_name, person.last_name, person.national_id,
                person.employment_type, person.org_unit, person.location,
                person.position_no, person.position_title,
            )
            for person in ds.persons
        ),
        "positions": sorted(
            (
                position.position_no, position.title, position.org_unit, position.location,
                position.position_type, position.occupant_personnel_no,
            )
            for position in ds.positions
        ),
        "summary": summary(ds),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def validate_target(
    ds: Dataset,
    database_path: Path,
    *,
    expected_personnel: int,
    expected_chart_fixed: int,
    expected_chart_named: int,
    expected_chart_total: int,
) -> dict[str, int | str]:
    database_path = database_path.resolve()
    validate_database_identity(database_path)
    ok, detail = sqlite_integrity(database_path)
    if not ok:
        raise RuntimeError(f"Target database integrity failed: {detail}")
    if len(ds.persons) != expected_personnel:
        raise ValueError(f"Personnel count mismatch: imported={len(ds.persons)}, expected={expected_personnel}.")

    with contextlib.closing(sqlite3.connect(f"file:{database_path.as_posix()}?mode=ro", uri=True)) as conn:
        target_people = {
            str(row[0]).strip(): str(row[1] or "").strip()
            for row in conn.execute("SELECT personnel_no,position_code FROM personnel")
        }
        source_people = {person.personnel_no: person.position_no for person in ds.persons}
        if set(source_people) != set(target_people):
            raise ValueError(
                "Personnel-number set mismatch: "
                f"source_only={len(set(source_people) - set(target_people))}, "
                f"target_only={len(set(target_people) - set(source_people))}."
            )
        position_mismatches = sum(
            bool(source_people[number]) and source_people[number] != target_people[number]
            for number in source_people
        )
        if position_mismatches:
            raise ValueError(f"Personnel position-code mismatch: {position_mismatches} record(s).")

        page = conn.execute(
            """SELECT approved_fixed_posts,approved_named_posts,approved_total_posts
               FROM chart_pages WHERE page_no=1"""
        ).fetchone()
        if page is None:
            raise ValueError("Approved chart page 1 is missing from the Enterprise target.")
        actual_chart = tuple(int(value or 0) for value in page)
        expected_chart = (expected_chart_fixed, expected_chart_named, expected_chart_total)
        if actual_chart != expected_chart:
            raise ValueError(f"Approved chart mismatch: target={actual_chart}, expected={expected_chart}.")

        unmatched_named = 0
        for position in ds.positions:
            row = conn.execute(
                "SELECT 1 FROM personnel WHERE personnel_no=? AND position_code=?",
                (position.occupant_personnel_no, position.position_no),
            ).fetchone()
            unmatched_named += row is None
        if unmatched_named:
            raise ValueError(f"Named-position mismatch against Enterprise target: {unmatched_named} record(s).")

        target_count = len(target_people)
        chart_pages = conn.execute("SELECT COUNT(*) FROM chart_pages").fetchone()[0]
    return {
        "target_personnel": target_count,
        "chart_pages": int(chart_pages),
        "approved_fixed_posts": actual_chart[0],
        "approved_named_posts": actual_chart[1],
        "approved_total_posts": actual_chart[2],
        "matched_named_assignments": len(ds.positions),
        "integrity": detail,
    }


def create_verified_backup(database_path: Path, backup_dir: Path) -> tuple[Path, str]:
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = backup_dir / f"pre-import-{stamp}.sqlite"
    if backup.exists():
        raise FileExistsError(f"Refusing to overwrite an existing backup: {backup}")
    with (
        contextlib.closing(sqlite3.connect(database_path)) as source,
        contextlib.closing(sqlite3.connect(backup)) as target,
    ):
        source.backup(target)
    ok, detail = sqlite_integrity(backup)
    if not ok:
        backup.unlink(missing_ok=True)
        raise RuntimeError(f"Pre-import backup integrity failed: {detail}")
    digest = sha256_file(backup)
    backup.with_suffix(backup.suffix + ".sha256").write_text(
        f"{digest}  {backup.name}\n", encoding="ascii"
    )
    return backup, digest


def restore_verified_backup(database_path: Path, backup_path: Path, expected_digest: str) -> None:
    if sha256_file(backup_path) != expected_digest:
        raise RuntimeError("Automatic rollback blocked because the backup hash changed.")
    staged = database_path.with_suffix(database_path.suffix + ".rollback-staged")
    shutil.copy2(backup_path, staged)
    ok, detail = sqlite_integrity(staged)
    if not ok:
        staged.unlink(missing_ok=True)
        raise RuntimeError(f"Automatic rollback staging failed: {detail}")
    os.replace(staged, database_path)
    for suffix in ("-wal", "-shm"):
        database_path.with_name(database_path.name + suffix).unlink(missing_ok=True)


def apply_to_enterprise(
    ds: Dataset,
    database_path: Path,
    backup_dir: Path,
    *,
    confirmation: str,
    expected_personnel: int = 1356,
    expected_chart_fixed: int = 536,
    expected_chart_named: int = 32,
    expected_chart_total: int = 568,
    actor_id: str | None = None,
) -> dict[str, object]:
    if confirmation != CONFIRMATION:
        raise PermissionError(f"Production apply requires confirmation token {CONFIRMATION!r}.")
    if any(issue.severity == "error" for issue in ds.issues):
        raise ValueError("Production apply is blocked while reconciliation has errors.")
    database_path = database_path.resolve()
    preflight = validate_target(
        ds, database_path,
        expected_personnel=expected_personnel,
        expected_chart_fixed=expected_chart_fixed,
        expected_chart_named=expected_chart_named,
        expected_chart_total=expected_chart_total,
    )
    backup, backup_digest = create_verified_backup(database_path, backup_dir.resolve())
    digest = source_digest(ds)
    try:
        repo = Repository(database_path)
        applied = repo.apply_real_data_import(
            [
                {
                    "personnel_no": person.personnel_no,
                    "first_name": person.first_name,
                    "last_name": person.last_name,
                    "org_unit": person.org_unit,
                    "position_no": person.position_no,
                    "position_title": person.position_title,
                    "employment_type": person.employment_type,
                    "location": person.location,
                }
                for person in ds.persons
            ],
            [
                {
                    "position_no": position.position_no,
                    "occupant_personnel_no": position.occupant_personnel_no,
                    "position_type": position.position_type,
                }
                for position in ds.positions
            ],
            source_name="four-approved-private-workbooks",
            source_digest=digest,
            warning_count=sum(issue.severity == "warning" for issue in ds.issues),
            actor_id=actor_id,
        )
        postflight = validate_target(
            ds, database_path,
            expected_personnel=expected_personnel,
            expected_chart_fixed=expected_chart_fixed,
            expected_chart_named=expected_chart_named,
            expected_chart_total=expected_chart_total,
        )
    except Exception:
        restore_verified_backup(database_path, backup, backup_digest)
        raise
    return {
        **applied,
        "backup_file": backup.name,
        "backup_sha256": backup_digest,
        "database_sha256": sha256_file(database_path),
        "preflight": preflight,
        "postflight": postflight,
    }
