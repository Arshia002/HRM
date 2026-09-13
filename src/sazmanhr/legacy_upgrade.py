"""Strict, backup-backed upgrade bridge for the proven alpha.4 database ancestor."""

from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import json
import os
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Iterable

from .config import DATABASE_FILENAME, PRODUCT_ID, SCHEMA_GENERATION, validate_database_identity
from .database import SCHEMA
from .migrations import MIGRATIONS, Migration, apply_migrations

LEGACY_PRODUCT_ID = "hrm-kepdco"
LEGACY_SCHEMA_GENERATION = "1"
LEGACY_SCHEMA_VERSION = "5"

ALPHA4_MIGRATION_PREFIX = {
    2: ("fine_grained_permissions", "3fa9d8d36edbaa09973c4111b630069b020e0d14009ef2577341323511e324a7"),
    3: ("backup_catalog_and_operations", "9f4de0f8c2f851241c1205a78154856e76f7d33427d0c84f6cf6dd02a8fda90f"),
    4: ("workflow_notifications", "5f37e01d7d136682fdccaad09a1dc75b05ba629f8db15fb51a81186f5f622092"),
    5: ("totp_mfa", "d35ff58c832d0f1afaf8b2e78ac5b5a86db837019e118787e21a064c8b44020c"),
}

CRITICAL_TABLES = ("users", "personnel", "chart_pages", "chart_nodes", "chart_lines")
WINDOWS_FILE_RETRY_ATTEMPTS = 8
WINDOWS_FILE_RETRY_SECONDS = 0.25


class LegacyUpgradeError(RuntimeError):
    pass


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sqlite_integrity(path: Path) -> tuple[bool, str]:
    try:
        with contextlib.closing(sqlite3.connect(path)) as conn:
            detail = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        return detail == "ok", detail
    except sqlite3.Error as exc:
        return False, str(exc)


def _metadata(conn: sqlite3.Connection) -> dict[str, str]:
    try:
        return dict(conn.execute("SELECT key,value FROM metadata"))
    except sqlite3.Error as exc:
        raise LegacyUpgradeError("Database metadata is unavailable.") from exc


def _migration_prefix(conn: sqlite3.Connection) -> dict[int, tuple[str, str]]:
    try:
        return {
            int(version): (str(name), str(checksum))
            for version, name, checksum in conn.execute(
                "SELECT version,name,checksum FROM schema_migrations ORDER BY version"
            )
        }
    except sqlite3.Error as exc:
        raise LegacyUpgradeError("Database migration history is unavailable.") from exc


def _critical_counts(conn: sqlite3.Connection) -> dict[str, int]:
    tables = {str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    missing = [name for name in CRITICAL_TABLES if name not in tables]
    if missing:
        raise LegacyUpgradeError(f"Legacy database is missing critical table(s): {missing!r}")
    return {
        name: int(conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0])
        for name in CRITICAL_TABLES
    }


def classify_database(database_path: Path) -> str:
    database_path = Path(database_path).resolve()
    if not database_path.is_file():
        raise LegacyUpgradeError(f"Database file does not exist: {database_path}")

    ok, detail = _sqlite_integrity(database_path)
    if not ok:
        raise LegacyUpgradeError(f"Database integrity check failed: {detail}")

    with contextlib.closing(sqlite3.connect(database_path)) as conn:
        metadata = _metadata(conn)
        if metadata.get("product_id") == PRODUCT_ID and metadata.get("schema_generation") == SCHEMA_GENERATION:
            validate_database_identity(database_path)
            return "current"
        if metadata.get("product_id") != LEGACY_PRODUCT_ID:
            raise LegacyUpgradeError(f"Unsupported legacy product_id: {metadata.get('product_id')!r}")
        if metadata.get("schema_generation") != LEGACY_SCHEMA_GENERATION:
            raise LegacyUpgradeError(
                f"Unsupported legacy schema_generation: {metadata.get('schema_generation')!r}"
            )
        if metadata.get("schema_version") != LEGACY_SCHEMA_VERSION:
            raise LegacyUpgradeError(f"Unsupported legacy schema_version: {metadata.get('schema_version')!r}")
        actual = _migration_prefix(conn)
        if actual != ALPHA4_MIGRATION_PREFIX:
            raise LegacyUpgradeError(
                "Legacy migration history does not exactly match the proven alpha.4 ancestor."
            )
        _critical_counts(conn)
        return "alpha4"


def _create_verified_backup(database_path: Path, backup_dir: Path) -> tuple[Path, str]:
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup = backup_dir / f"pre-alpha4-upgrade-{stamp}.sqlite"
    if backup.exists():
        raise FileExistsError(f"Refusing to overwrite existing backup: {backup}")
    with (
        contextlib.closing(sqlite3.connect(database_path)) as source,
        contextlib.closing(sqlite3.connect(backup)) as target,
    ):
        source.backup(target)
    ok, detail = _sqlite_integrity(backup)
    if not ok:
        backup.unlink(missing_ok=True)
        raise LegacyUpgradeError(f"Upgrade backup integrity failed: {detail}")
    digest = _sha256_file(backup)
    backup.with_suffix(backup.suffix + ".sha256").write_text(
        f"{digest}  {backup.name}\n", encoding="ascii"
    )
    return backup, digest


def _replace_with_retry(source: Path, destination: Path) -> None:
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
    if last_error is None:  # pragma: no cover
        raise RuntimeError("Database replacement ended without a result.")
    raise last_error


def _write_state(state_path: Path, payload: dict[str, object]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    staged = state_path.with_suffix(state_path.suffix + ".staged")
    staged.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    os.replace(staged, state_path)


def _load_state(state_path: Path) -> dict[str, object]:
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LegacyUpgradeError("Database upgrade state file is invalid.") from exc
    if not isinstance(payload, dict) or payload.get("schema") != 1:
        raise LegacyUpgradeError("Database upgrade state schema is invalid.")
    return payload


def restore_legacy_database_upgrade(state_path: Path) -> dict[str, object]:
    state_path = Path(state_path).resolve()
    if not state_path.exists():
        return {"ok": True, "restored": False, "reason": "state_missing"}

    state = _load_state(state_path)
    if bool(state.get("committed", False)):
        return {"ok": True, "restored": False, "reason": "transaction_committed"}
    if not state.get("performed"):
        return {"ok": True, "restored": False, "reason": "migration_not_performed"}

    database_path = Path(str(state.get("database", ""))).resolve()
    backup_path = Path(str(state.get("backup", ""))).resolve()
    expected_digest = str(state.get("backup_sha256", ""))
    if not backup_path.is_file() or len(expected_digest) != 64:
        raise LegacyUpgradeError("Database upgrade rollback state is incomplete.")
    if _sha256_file(backup_path) != expected_digest:
        raise LegacyUpgradeError(
            "Automatic rollback blocked because the upgrade backup hash changed."
        )

    staged = database_path.with_suffix(database_path.suffix + ".rollback-staged")
    staged.unlink(missing_ok=True)
    shutil.copy2(backup_path, staged)
    ok, detail = _sqlite_integrity(staged)
    if not ok:
        staged.unlink(missing_ok=True)
        raise LegacyUpgradeError(f"Automatic rollback staging failed: {detail}")

    _replace_with_retry(staged, database_path)
    for suffix in ("-wal", "-shm"):
        database_path.with_name(database_path.name + suffix).unlink(missing_ok=True)

    if classify_database(database_path) != "alpha4":
        raise LegacyUpgradeError("Restored database did not validate as the alpha.4 ancestor.")

    expected_counts = state.get("critical_counts")
    if isinstance(expected_counts, dict):
        with contextlib.closing(sqlite3.connect(database_path)) as conn:
            actual_counts = _critical_counts(conn)
        normalized_expected = {str(k): int(v) for k, v in expected_counts.items()}
        if actual_counts != normalized_expected:
            raise LegacyUpgradeError(
                "Restored database critical row counts do not match the pre-upgrade snapshot."
            )

    state["status"] = "rolled_back"
    _write_state(state_path, state)
    return {
        "ok": True,
        "restored": True,
        "database": str(database_path),
        "backup": str(backup_path),
        "backup_sha256": expected_digest,
    }


def commit_legacy_database_upgrade(state_path: Path) -> dict[str, object]:
    state_path = Path(state_path).resolve()
    state = _load_state(state_path)

    if not bool(state.get("performed")):
        raise LegacyUpgradeError(
            "Database upgrade transaction cannot be committed because no migration was performed."
        )
    if state.get("status") != "upgraded":
        raise LegacyUpgradeError(
            "Database upgrade transaction can only be committed after status is upgraded."
        )

    if bool(state.get("committed", False)):
        return {
            "ok": True,
            "committed": True,
            "database": str(state.get("database", "")),
            "backup": str(state.get("backup", "")),
            "backup_sha256": str(state.get("backup_sha256", "")),
        }

    state["committed"] = True
    _write_state(state_path, state)
    return {
        "ok": True,
        "committed": True,
        "database": str(state.get("database", "")),
        "backup": str(state.get("backup", "")),
        "backup_sha256": str(state.get("backup_sha256", "")),
    }


def upgrade_legacy_database(
    data_dir: Path,
    state_path: Path,
    *,
    migrations: Iterable[Migration] = MIGRATIONS,
) -> dict[str, object]:
    data_dir = Path(data_dir).resolve()
    database_path = data_dir / DATABASE_FILENAME
    state_path = Path(state_path).resolve()

    classification = classify_database(database_path)
    if classification == "current":
        _write_state(
            state_path,
            {"schema": 1, "performed": False, "status": "current", "database": str(database_path)},
        )
        return {
            "ok": True,
            "performed": False,
            "classification": "current",
            "database": str(database_path),
        }

    with contextlib.closing(sqlite3.connect(database_path)) as conn:
        critical_counts = _critical_counts(conn)

    backup, backup_digest = _create_verified_backup(
        database_path, data_dir / "backups" / "upgrade-transactions"
    )
    state: dict[str, object] = {
        "schema": 1,
        "performed": True,
        "status": "prepared",
        "database": str(database_path),
        "backup": str(backup),
        "backup_sha256": backup_digest,
        "critical_counts": critical_counts,
        "source": {
            "product_id": LEGACY_PRODUCT_ID,
            "schema_generation": LEGACY_SCHEMA_GENERATION,
            "schema_version": LEGACY_SCHEMA_VERSION,
        },
    }
    _write_state(state_path, state)

    try:
        with contextlib.closing(sqlite3.connect(database_path)) as conn:
            conn.execute("PRAGMA foreign_keys=ON")
            conn.executescript(SCHEMA)
            latest = apply_migrations(conn, migrations)
            after_counts = _critical_counts(conn)
            if after_counts != critical_counts:
                raise LegacyUpgradeError(
                    "Critical business row counts changed during legacy schema migration."
                )
            integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
            if integrity != "ok":
                raise LegacyUpgradeError(f"Post-migration integrity check failed: {integrity}")
            foreign_key_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
            if foreign_key_errors:
                raise LegacyUpgradeError(
                    f"Post-migration foreign key check failed: {foreign_key_errors[:5]!r}"
                )
            conn.execute(
                "INSERT OR REPLACE INTO metadata(key,value) VALUES('product_id',?)", (PRODUCT_ID,)
            )
            conn.execute(
                "INSERT OR REPLACE INTO metadata(key,value) VALUES('schema_generation',?)",
                (SCHEMA_GENERATION,),
            )
            conn.commit()

        validate_database_identity(database_path)
        state["status"] = "upgraded"
        state["target"] = {
            "product_id": PRODUCT_ID,
            "schema_generation": SCHEMA_GENERATION,
            "schema_version": str(latest),
        }
        _write_state(state_path, state)
        return {
            "ok": True,
            "performed": True,
            "classification": "alpha4",
            "database": str(database_path),
            "backup": str(backup),
            "backup_sha256": backup_digest,
            "schema_version": int(latest),
            "critical_counts": critical_counts,
        }
    except Exception:
        restore_legacy_database_upgrade(state_path)
        raise
