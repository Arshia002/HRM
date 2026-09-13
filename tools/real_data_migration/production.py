from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from sazmanhr.config import validate_database_identity  # noqa: E402
from sazmanhr.database import Repository, utc_now  # noqa: E402
from sazmanhr.operations import sqlite_integrity  # noqa: E402

from .models import Dataset, Issue  # noqa: E402
from .reconcile import summary  # noqa: E402


CONFIRMATION = "APPLY-TO-HRM"
WINDOWS_FILE_RETRY_ATTEMPTS = 20
WINDOWS_FILE_RETRY_SECONDS = 0.1


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
    expected_page_16_total: int = 24,
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

        page_16 = conn.execute(
            "SELECT approved_total_posts FROM chart_pages WHERE page_no=16"
        ).fetchone()
        if page_16 is None:
            raise ValueError("Approved chart page 16 is missing from the Enterprise target.")
        actual_page_16_total = int(page_16[0] or 0)
        if actual_page_16_total != expected_page_16_total:
            raise ValueError(
                "Approved page-16 post count mismatch: "
                f"target={actual_page_16_total}, expected={expected_page_16_total}."
            )

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
        "approved_page_16_total": actual_page_16_total,
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


def replace_with_retry(source: Path, destination: Path) -> None:
    """Replace a database file after transient Windows scanners release it.

    SQLite connections are explicitly closed before this function is called.
    Windows can nevertheless return access-denied briefly while Defender or an
    indexing filter still holds a non-delete-sharing handle. Retry only the
    transient permission case, keep the interval bounded, and re-raise the
    original failure if the file never becomes replaceable.
    """
    last_error: PermissionError | None = None
    for attempt in range(WINDOWS_FILE_RETRY_ATTEMPTS):
        try:
            os.replace(source, destination)
            return
        except PermissionError as exc:
            last_error = exc
            if attempt + 1 == WINDOWS_FILE_RETRY_ATTEMPTS:
                break
            time.sleep(WINDOWS_FILE_RETRY_SECONDS)
    if last_error is None:  # pragma: no cover - loop always attempts replace
        raise RuntimeError("Database replacement ended without a result.")
    raise last_error


def restore_verified_backup(database_path: Path, backup_path: Path, expected_digest: str) -> None:
    if sha256_file(backup_path) != expected_digest:
        raise RuntimeError("Automatic rollback blocked because the backup hash changed.")
    staged = database_path.with_suffix(database_path.suffix + ".rollback-staged")
    shutil.copy2(backup_path, staged)
    ok, detail = sqlite_integrity(staged)
    if not ok:
        staged.unlink(missing_ok=True)
        raise RuntimeError(f"Automatic rollback staging failed: {detail}")
    replace_with_retry(staged, database_path)
    for suffix in ("-wal", "-shm"):
        database_path.with_name(database_path.name + suffix).unlink(missing_ok=True)


def _initial_person_id(personnel_no: str) -> str:
    """Return a deterministic opaque id for the private initial candidate."""
    return "initial-person-" + hashlib.sha256(personnel_no.encode("utf-8")).hexdigest()[:20]


def _remove_sqlite_family(database_path: Path) -> None:
    for suffix in ("", "-wal", "-shm"):
        database_path.with_name(database_path.name + suffix).unlink(missing_ok=True)


def build_initial_enterprise_candidate(
    ds: Dataset,
    seed_database: Path,
    candidate_database: Path,
    backup_dir: Path,
    *,
    confirmation: str,
    expected_personnel: int = 1356,
    expected_chart_fixed: int = 536,
    expected_chart_named: int = 32,
    expected_chart_total: int = 568,
    expected_page_16_total: int = 24,
    actor_id: str | None = None,
) -> dict[str, object]:
    """Build a private production-shaped candidate from the public clean seed.

    The bundled seed intentionally contains synthetic personnel. The normal
    production import cannot bootstrap from it because apply_real_data_import()
    requires exact source/target personnel-number set equality. This function
    creates that exact set only in an offline candidate database, then delegates
    the existing production refresh/validation/backup/audit behavior to
    apply_to_enterprise().

    The live database is never modified here. Any incomplete candidate is
    removed on failure.
    """
    if confirmation != CONFIRMATION:
        raise PermissionError(
            f"Initial production provisioning requires confirmation token {CONFIRMATION!r}."
        )
    if any(issue.severity == "error" for issue in ds.issues):
        raise ValueError(
            "Initial production provisioning is blocked while reconciliation has errors."
        )
    if len(ds.persons) != expected_personnel:
        raise ValueError(
            f"Personnel count mismatch: imported={len(ds.persons)}, expected={expected_personnel}."
        )

    personnel_numbers = [str(person.personnel_no or "").strip() for person in ds.persons]
    if (
        not personnel_numbers
        or any(not number for number in personnel_numbers)
        or len(set(personnel_numbers)) != len(personnel_numbers)
    ):
        raise ValueError(
            "Initial production provisioning requires unique, non-empty personnel numbers."
        )

    seed_database = seed_database.resolve()
    candidate_database = candidate_database.resolve()
    backup_dir = backup_dir.resolve()

    if seed_database == candidate_database:
        raise ValueError(
            "Initial production candidate must not overwrite the bundled seed database."
        )
    if candidate_database.exists():
        raise FileExistsError(
            f"Refusing to overwrite an existing candidate database: {candidate_database}"
        )

    validate_database_identity(seed_database)
    candidate_database.parent.mkdir(parents=True, exist_ok=True)

    try:
        shutil.copy2(seed_database, candidate_database)
        validate_database_identity(candidate_database)

        repo = Repository(candidate_database)
        now = utc_now()

        with repo.write() as conn:
            existing_tables = {
                str(row[0])
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }

            for table in (
                "personnel_movements",
                "personnel_assignments",
                "positions",
                "organizational_units",
                "personnel",
                "import_batches",
                "audit_log",
                "change_feed",
                "ui_monthly_assignments",
                "ui_status_snapshots",
                "ui_compat_datasets",
            ):
                if table in existing_tables:
                    conn.execute(f"DELETE FROM {table}")

            conn.execute(
                """UPDATE chart_pages
                   SET approved_fixed_posts=?,approved_named_posts=?,approved_total_posts=?
                   WHERE page_no=1""",
                (expected_chart_fixed, expected_chart_named, expected_chart_total),
            )
            conn.execute(
                "UPDATE chart_pages SET approved_total_posts=? WHERE page_no=16",
                (expected_page_16_total,),
            )
            conn.execute("DELETE FROM metadata WHERE key='seed_mode'")
            conn.execute(
                "INSERT OR REPLACE INTO metadata(key,value) "
                "VALUES('dataset_kind','protected-real-data-candidate')"
            )
            conn.execute(
                "INSERT OR REPLACE INTO metadata(key,value) "
                "VALUES('dataset_personnel_count',?)",
                (str(expected_personnel),),
            )

            for index, person in enumerate(ds.persons, start=1):
                personnel_no = str(person.personnel_no).strip()
                position_no = str(person.position_no or "").strip()
                position_title = str(person.position_title or "").strip()
                org_unit = str(person.org_unit or "").strip()
                location = str(person.location or "").strip()
                conn.execute(
                    """INSERT INTO personnel(
                       id,personnel_no,first_name,last_name,full_name,gender,organizational_unit,
                       position_code,position_title,employment_group,employment_subtype,status,
                       activity_area,actual_location,company,chart_page_no,chart_node_id,extra_json,
                       row_version,updated_at,updated_by)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        _initial_person_id(personnel_no),
                        personnel_no,
                        "",
                        "",
                        f"initial-provision-{index}",
                        "",
                        org_unit,
                        position_no,
                        position_title,
                        "",
                        "",
                        "",
                        "",
                        location,
                        "",
                        None,
                        "",
                        "{}",
                        1,
                        now,
                        actor_id,
                    ),
                )

        repo.initialize()

        result = apply_to_enterprise(
            ds,
            candidate_database,
            backup_dir,
            confirmation=confirmation,
            expected_personnel=expected_personnel,
            expected_chart_fixed=expected_chart_fixed,
            expected_chart_named=expected_chart_named,
            expected_chart_total=expected_chart_total,
            expected_page_16_total=expected_page_16_total,
            actor_id=actor_id,
        )
        return {
            **result,
            "candidate_file": candidate_database.name,
            "candidate_sha256": sha256_file(candidate_database),
            "provisioned_personnel": expected_personnel,
        }
    except Exception:
        _remove_sqlite_family(candidate_database)
        raise


def _validate_initial_candidate_for_promotion(
    database_path: Path,
    expected_personnel: int,
) -> dict[str, object]:
    validate_database_identity(database_path)
    ok, detail = sqlite_integrity(database_path)
    if not ok:
        raise RuntimeError(f"Candidate database integrity failed: {detail}")

    with contextlib.closing(sqlite3.connect(database_path)) as conn:
        foreign_keys = conn.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_keys:
            raise RuntimeError(
                f"Candidate database foreign-key validation failed: {len(foreign_keys)} violation(s)."
            )
        actual_personnel = int(
            conn.execute("SELECT COUNT(*) FROM personnel").fetchone()[0]
        )
        if actual_personnel != expected_personnel:
            raise ValueError(
                f"Personnel count mismatch: candidate={actual_personnel}, expected={expected_personnel}."
            )
        metadata = dict(
            conn.execute(
                "SELECT key,value FROM metadata "
                "WHERE key IN ('dataset_kind','seed_mode','dataset_personnel_count')"
            )
        )

    if metadata.get("dataset_kind") != "protected-real-data-candidate":
        raise ValueError(
            "Candidate database is not marked as a protected real-data candidate."
        )
    if metadata.get("seed_mode") == "synthetic-demo":
        raise ValueError("Synthetic-demo database cannot be promoted as real production data.")
    declared_count = metadata.get("dataset_personnel_count")
    if declared_count is not None and str(declared_count) != str(expected_personnel):
        raise ValueError(
            "Candidate dataset_personnel_count metadata does not match the expected personnel count."
        )

    return {
        "personnel": actual_personnel,
        "integrity": "ok",
        "foreign_key_errors": 0,
        "dataset_kind": metadata.get("dataset_kind"),
    }


def promote_initial_enterprise_candidate(
    candidate_database: Path,
    database_path: Path,
    backup_dir: Path,
    *,
    expected_personnel: int = 1356,
) -> dict[str, object]:
    """Atomically promote a validated offline candidate into the live DB path.

    The caller must ensure the HRM service and all writers are stopped before
    promotion. The candidate is copied to a staged file in the live directory,
    verified, atomically replaced into the canonical path, and postflight-
    verified. Any failure after the live backup exists restores that backup.
    """
    candidate_database = candidate_database.resolve()
    database_path = database_path.resolve()
    backup_dir = backup_dir.resolve()

    if candidate_database == database_path:
        raise ValueError("Candidate and live database paths must be different.")
    if expected_personnel <= 0:
        raise ValueError("expected_personnel must be positive.")

    candidate_preflight = _validate_initial_candidate_for_promotion(
        candidate_database,
        expected_personnel,
    )
    candidate_digest = sha256_file(candidate_database)

    validate_database_identity(database_path)
    live_ok, live_detail = sqlite_integrity(database_path)
    if not live_ok:
        raise RuntimeError(f"Live database integrity failed before promotion: {live_detail}")

    staged = database_path.with_name(f".{database_path.name}.initial-promotion-staged")
    if staged.exists():
        raise FileExistsError(
            f"Refusing to overwrite stale promotion staging file: {staged}"
        )

    backup: Path | None = None
    backup_digest = ""
    try:
        backup, backup_digest = create_verified_backup(database_path, backup_dir)

        shutil.copy2(candidate_database, staged)
        if sha256_file(staged) != candidate_digest:
            raise RuntimeError("Staged candidate hash verification failed.")
        _validate_initial_candidate_for_promotion(staged, expected_personnel)

        replace_with_retry(staged, database_path)
        for suffix in ("-wal", "-shm"):
            database_path.with_name(database_path.name + suffix).unlink(missing_ok=True)

        postflight = _validate_initial_candidate_for_promotion(
            database_path,
            expected_personnel,
        )
        promoted_digest = sha256_file(database_path)
        if promoted_digest != candidate_digest:
            raise RuntimeError("Promoted database hash does not match the validated candidate.")

        return {
            "backup_file": backup.name,
            "backup_sha256": backup_digest,
            "promoted_sha256": promoted_digest,
            "personnel": postflight["personnel"],
            "integrity": postflight["integrity"],
            "foreign_key_errors": postflight["foreign_key_errors"],
            "candidate_preflight": candidate_preflight,
        }
    except Exception:
        staged.unlink(missing_ok=True)
        if backup is not None:
            restore_verified_backup(database_path, backup, backup_digest)
        raise
    finally:
        staged.unlink(missing_ok=True)

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
    expected_page_16_total: int = 24,
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
        expected_page_16_total=expected_page_16_total,
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
            expected_page_16_total=expected_page_16_total,
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
