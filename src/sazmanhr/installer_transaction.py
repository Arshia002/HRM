"""Durable coordinator for installer database + Windows Service upgrade transactions."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from .legacy_upgrade import (
    commit_legacy_database_upgrade,
    restore_legacy_database_upgrade,
)
from .windows_service_control import (
    load_service_cutover_journal,
    mark_service_cutover_committed,
    recover_windows_service_cutover,
)

DatabaseAction = Callable[[Path], dict[str, object]]
ServiceAction = Callable[[Path], dict[str, object]]


def recover_upgrade_transaction(
    service_state_path: Path,
    database_state_path: Path,
    *,
    restore_database: DatabaseAction = restore_legacy_database_upgrade,
    recover_service: ServiceAction = recover_windows_service_cutover,
    commit_database: DatabaseAction = commit_legacy_database_upgrade,
) -> dict[str, object]:
    """Recover or finalize an interrupted installer transaction.

    The service journal is the durable decision coordinator:
    - uncommitted service journal => rollback DB first, then service;
    - committed service journal => never roll back; finalize DB commit instead.
    """
    service_state_path = Path(service_state_path).resolve()
    database_state_path = Path(database_state_path).resolve()

    if not service_state_path.is_file():
        return {
            "ok": True,
            "decision": "none",
            "database_recovered": False,
            "database_committed": False,
            "service_recovered": False,
            "reason": "service_state_missing",
        }

    service_state = load_service_cutover_journal(service_state_path)
    committed = bool(service_state.get("committed")) or service_state.get("phase") == "committed"

    if committed:
        database_committed = False
        if database_state_path.is_file():
            commit_database(database_state_path)
            database_committed = True
        return {
            "ok": True,
            "decision": "commit",
            "database_recovered": False,
            "database_committed": database_committed,
            "service_recovered": False,
        }

    if service_state.get("phase") == "recovered":
        return {
            "ok": True,
            "decision": "rollback",
            "database_recovered": False,
            "database_committed": False,
            "service_recovered": False,
            "reason": "already_recovered",
        }

    # Rollback order is deliberate: an old service must never be started
    # against a database that failed to return to its old generation.
    database_result = restore_database(database_state_path)
    service_result = recover_service(service_state_path)

    return {
        "ok": True,
        "decision": "rollback",
        "database_recovered": bool(database_result.get("restored", False)),
        "database_committed": False,
        "service_recovered": service_result.get("phase") == "recovered",
    }


def commit_upgrade_transaction(
    service_state_path: Path,
    database_state_path: Path,
    *,
    commit_service: ServiceAction = mark_service_cutover_committed,
    commit_database: DatabaseAction = commit_legacy_database_upgrade,
) -> dict[str, object]:
    """Persist the commit decision before finalizing the database transaction.

    Once the service journal is committed, recovery must only move forward.
    Therefore the service commit is intentionally written before DB commit.
    """
    service_state_path = Path(service_state_path).resolve()
    database_state_path = Path(database_state_path).resolve()

    service_result = commit_service(service_state_path)
    service_committed = bool(service_result.get("committed")) or (
        service_result.get("phase") == "committed"
    )
    if not service_committed:
        raise RuntimeError("Service cutover commit did not persist the commit decision.")

    database_committed = False
    if database_state_path.is_file():
        database_result = commit_database(database_state_path)
        database_committed = bool(database_result.get("committed", False))
        if not database_committed:
            raise RuntimeError("Database upgrade commit did not persist.")

    return {
        "ok": True,
        "decision": "commit",
        "service_committed": True,
        "database_committed": database_committed,
    }
