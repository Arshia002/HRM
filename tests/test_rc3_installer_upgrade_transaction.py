from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sazmanhr.installer_transaction import (
    commit_upgrade_transaction,
    recover_upgrade_transaction,
)
from sazmanhr.windows_service_control import (
    advance_service_cutover_journal,
    create_service_cutover_journal,
    mark_service_cutover_committed,
)


class Rc3InstallerUpgradeTransactionTests(unittest.TestCase):
    def _service_snapshot(self) -> dict[str, object]:
        return {
            "service_name": "HRMCentralService",
            "original_image_path": r'"C:\Program Files\SazmanHR Enterprise\ServiceRuntime\svc-old\HRMService.exe"',
            "original_executable": r"C:\Program Files\SazmanHR Enterprise\ServiceRuntime\svc-old\HRMService.exe",
            "original_start_type": 2,
            "original_object_name": r"NT AUTHORITY\LocalService",
            "original_sid_type": 1,
            "was_running": True,
            "target_executable": r"C:\Program Files\SazmanHR Enterprise\ServiceRuntime\svc-new\HRMService.exe",
        }

    def _make_uncommitted_service_journal(self, path: Path) -> None:
        create_service_cutover_journal(path, self._service_snapshot())
        advance_service_cutover_journal(path, "service_stopped")
        advance_service_cutover_journal(path, "image_switched")

    def _make_committed_service_journal(self, path: Path) -> None:
        create_service_cutover_journal(path, self._service_snapshot())
        for phase in ("service_stopped", "image_switched", "service_started", "ready"):
            advance_service_cutover_journal(path, phase)
        mark_service_cutover_committed(path)

    def test_uncommitted_recovery_restores_database_before_service(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            service_state = root / "service-cutover-state.json"
            database_state = root / "installer-upgrade-state.json"
            database_state.write_text("{}", encoding="utf-8")
            self._make_uncommitted_service_journal(service_state)
            events: list[str] = []

            result = recover_upgrade_transaction(
                service_state,
                database_state,
                restore_database=lambda path: events.append("database") or {
                    "ok": True,
                    "restored": True,
                },
                recover_service=lambda path: events.append("service") or {
                    "phase": "recovered",
                    "committed": False,
                },
            )

            self.assertEqual(events, ["database", "service"])
            self.assertEqual(result["decision"], "rollback")
            self.assertTrue(result["database_recovered"])
            self.assertTrue(result["service_recovered"])

    def test_database_recovery_failure_blocks_service_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            service_state = root / "service-cutover-state.json"
            database_state = root / "installer-upgrade-state.json"
            database_state.write_text("{}", encoding="utf-8")
            self._make_uncommitted_service_journal(service_state)
            service_calls: list[str] = []

            def fail_database(_path: Path) -> dict[str, object]:
                raise RuntimeError("synthetic database rollback failure")

            with self.assertRaisesRegex(RuntimeError, "database rollback failure"):
                recover_upgrade_transaction(
                    service_state,
                    database_state,
                    restore_database=fail_database,
                    recover_service=lambda path: service_calls.append(str(path)) or {
                        "phase": "recovered",
                        "committed": False,
                    },
                )

            self.assertEqual(service_calls, [])

    def test_commit_decision_is_persisted_before_database_commit(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            service_state = root / "service-cutover-state.json"
            database_state = root / "installer-upgrade-state.json"
            database_state.write_text("{}", encoding="utf-8")
            self._make_uncommitted_service_journal(service_state)
            # Move to ready so the service journal can become the durable coordinator.
            advance_service_cutover_journal(service_state, "service_started")
            advance_service_cutover_journal(service_state, "ready")
            events: list[str] = []

            result = commit_upgrade_transaction(
                service_state,
                database_state,
                commit_service=lambda path: events.append("service-commit") or {
                    "phase": "committed",
                    "committed": True,
                },
                commit_database=lambda path: events.append("database-commit") or {
                    "ok": True,
                    "committed": True,
                },
            )

            self.assertEqual(events, ["service-commit", "database-commit"])
            self.assertEqual(result["decision"], "commit")
            self.assertTrue(result["service_committed"])
            self.assertTrue(result["database_committed"])

    def test_committed_service_journal_finalizes_database_instead_of_rolling_back(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            service_state = root / "service-cutover-state.json"
            database_state = root / "installer-upgrade-state.json"
            database_state.write_text("{}", encoding="utf-8")
            self._make_committed_service_journal(service_state)
            events: list[str] = []

            result = recover_upgrade_transaction(
                service_state,
                database_state,
                restore_database=lambda path: events.append("database-restore") or {
                    "ok": True,
                    "restored": True,
                },
                recover_service=lambda path: events.append("service-restore") or {
                    "phase": "recovered",
                    "committed": False,
                },
                commit_database=lambda path: events.append("database-commit") or {
                    "ok": True,
                    "committed": True,
                },
            )

            self.assertEqual(events, ["database-commit"])
            self.assertEqual(result["decision"], "commit")
            self.assertTrue(result["database_committed"])
            self.assertFalse(result["service_recovered"])

    def test_committed_decision_survives_database_commit_failure(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            service_state = root / "service-cutover-state.json"
            database_state = root / "installer-upgrade-state.json"
            database_state.write_text("{}", encoding="utf-8")
            self._make_uncommitted_service_journal(service_state)
            advance_service_cutover_journal(service_state, "service_started")
            advance_service_cutover_journal(service_state, "ready")

            def fail_database_commit(_path: Path) -> dict[str, object]:
                raise RuntimeError("synthetic database commit failure")

            with self.assertRaisesRegex(RuntimeError, "database commit failure"):
                commit_upgrade_transaction(
                    service_state,
                    database_state,
                    commit_service=mark_service_cutover_committed,
                    commit_database=fail_database_commit,
                )

            # A later recovery must observe the durable commit decision and finalize,
            # never roll the service/database back.
            events: list[str] = []
            result = recover_upgrade_transaction(
                service_state,
                database_state,
                restore_database=lambda path: events.append("database-restore") or {
                    "ok": True,
                    "restored": True,
                },
                recover_service=lambda path: events.append("service-restore") or {
                    "phase": "recovered",
                    "committed": False,
                },
                commit_database=lambda path: events.append("database-commit") or {
                    "ok": True,
                    "committed": True,
                },
            )

            self.assertEqual(events, ["database-commit"])
            self.assertEqual(result["decision"], "commit")


if __name__ == "__main__":
    unittest.main()
