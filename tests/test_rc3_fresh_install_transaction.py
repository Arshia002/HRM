from __future__ import annotations

import json
import tempfile
import unittest
from unittest.mock import Mock, patch
from pathlib import Path

from sazmanhr.installer_transaction import (
    commit_upgrade_transaction,
    recover_upgrade_transaction,
)
from sazmanhr.windows_service_control import (
    SERVICE_RUNNING,
    cleanup_fresh_install_firewall,
    advance_service_cutover_journal,
    create_service_cutover_journal,
    create_windows_service_install_journal,
    load_service_cutover_journal,
    mark_service_cutover_committed,
    recover_windows_service_cutover,
)


class Rc3FreshInstallTransactionTests(unittest.TestCase):
    def _target(self) -> str:
        return r"C:\Program Files\SazmanHR Enterprise\ServiceRuntime\svc-new\HRMService.exe"

    def _fresh_state(self, path: Path) -> None:
        create_windows_service_install_journal(
            path,
            "HRMCentralService",
            self._target(),
            state_reader=lambda _name: None,
        )

    def test_prepare_fresh_install_journal_records_service_absence(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_path = Path(td) / "service-cutover-state.json"

            state = create_windows_service_install_journal(
                state_path,
                "HRMCentralService",
                self._target(),
                state_reader=lambda _name: None,
            )

            self.assertFalse(state["service_existed_before"])
            self.assertFalse(state["was_running"])
            self.assertIsNone(state["original_image_path"])
            self.assertIsNone(state["original_executable"])
            self.assertIsNone(state["original_start_type"])
            self.assertIsNone(state["original_object_name"])
            self.assertIsNone(state["original_sid_type"])
            self.assertEqual(state["phase"], "snapshotted")
            self.assertFalse(state["committed"])

            persisted = load_service_cutover_journal(state_path)
            self.assertFalse(persisted["service_existed_before"])

    def test_prepare_fresh_install_refuses_to_replace_existing_service(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_path = Path(td) / "service-cutover-state.json"

            with self.assertRaisesRegex(RuntimeError, "already exists"):
                create_windows_service_install_journal(
                    state_path,
                    "HRMCentralService",
                    self._target(),
                    state_reader=lambda _name: SERVICE_RUNNING,
                )

            self.assertFalse(state_path.exists())

    def test_fresh_install_recovery_deletes_new_service_without_restoring_old_config(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_path = Path(td) / "service-cutover-state.json"
            self._fresh_state(state_path)
            advance_service_cutover_journal(state_path, "service_stopped")
            advance_service_cutover_journal(state_path, "image_switched")
            events: list[str] = []

            recovered = recover_windows_service_cutover(
                state_path,
                stopper=lambda name: events.append(f"stop:{name}") or {"exists": True},
                deleter=lambda name: events.append(f"delete:{name}") or {
                    "exists": True,
                    "deleted": True,
                },
                image_setter=lambda *args: events.append("image") or {},
                configuration_restorer=lambda *args, **kwargs: events.append("config") or {},
                starter=lambda name: events.append(f"start:{name}") or {},
                fresh_cleanup=lambda: None,
            )

            self.assertEqual(
                events,
                [
                    "stop:HRMCentralService",
                    "delete:HRMCentralService",
                ],
            )
            self.assertEqual(recovered["phase"], "recovered")
            self.assertFalse(recovered["committed"])
            self.assertFalse(recovered["service_existed_before"])

            persisted = load_service_cutover_journal(state_path)
            self.assertEqual(persisted["phase"], "recovered")

    def test_firewall_cleanup_is_idempotent_when_rule_is_already_absent(self) -> None:
        delete_result = Mock(returncode=1, stdout="No rules match the specified criteria.")
        verify_result = Mock(returncode=1, stdout="No rules match the specified criteria.")

        with patch(
            "sazmanhr.windows_service_control.subprocess.run",
            side_effect=[delete_result, verify_result],
        ):
            cleanup_fresh_install_firewall()

    def test_firewall_cleanup_fails_closed_when_rule_remains(self) -> None:
        delete_result = Mock(returncode=1, stdout="synthetic delete failure")
        verify_result = Mock(
            returncode=0,
            stdout="Rule Name: HRM Central Service 8765\nEnabled: Yes\n",
        )

        with patch(
            "sazmanhr.windows_service_control.subprocess.run",
            side_effect=[delete_result, verify_result],
        ):
            with self.assertRaisesRegex(RuntimeError, "firewall cleanup failed"):
                cleanup_fresh_install_firewall()

    def test_fresh_install_recovery_cleans_firewall_before_marking_recovered(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_path = Path(td) / "service-cutover-state.json"
            self._fresh_state(state_path)
            for phase in ("service_stopped", "image_switched", "service_started"):
                advance_service_cutover_journal(state_path, phase)
            events: list[str] = []

            recovered = recover_windows_service_cutover(
                state_path,
                stopper=lambda name: events.append(f"stop:{name}") or {"exists": True},
                deleter=lambda name: events.append(f"delete:{name}") or {
                    "exists": True,
                    "deleted": True,
                },
                fresh_cleanup=lambda: events.append("firewall-cleanup"),
            )

            self.assertEqual(
                events,
                [
                    "stop:HRMCentralService",
                    "delete:HRMCentralService",
                    "firewall-cleanup",
                ],
            )
            self.assertEqual(recovered["phase"], "recovered")
            self.assertFalse(recovered["committed"])

    def test_fresh_install_firewall_cleanup_failure_does_not_mark_recovered(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_path = Path(td) / "service-cutover-state.json"
            self._fresh_state(state_path)
            for phase in ("service_stopped", "image_switched", "service_started"):
                advance_service_cutover_journal(state_path, phase)

            def fail_cleanup() -> None:
                raise RuntimeError("synthetic firewall cleanup failure")

            with self.assertRaisesRegex(RuntimeError, "firewall cleanup failure"):
                recover_windows_service_cutover(
                    state_path,
                    stopper=lambda _name: {"exists": True},
                    deleter=lambda _name: {"exists": True, "deleted": True},
                    fresh_cleanup=fail_cleanup,
                )

            persisted = load_service_cutover_journal(state_path)
            self.assertEqual(persisted["phase"], "service_started")
            self.assertFalse(persisted["committed"])

    def test_existing_service_recovery_does_not_run_fresh_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_path = Path(td) / "service-cutover-state.json"
            snapshot = {
                "service_name": "HRMCentralService",
                "original_image_path": r'"C:\Program Files\SazmanHR Enterprise\ServiceRuntime\svc-old\HRMService.exe"',
                "original_executable": r"C:\Program Files\SazmanHR Enterprise\ServiceRuntime\svc-old\HRMService.exe",
                "original_start_type": 2,
                "original_object_name": r"NT AUTHORITY\LocalService",
                "original_sid_type": 1,
                "was_running": True,
                "target_executable": self._target(),
            }
            create_service_cutover_journal(state_path, snapshot)
            advance_service_cutover_journal(state_path, "service_stopped")
            advance_service_cutover_journal(state_path, "image_switched")
            events: list[str] = []

            recovered = recover_windows_service_cutover(
                state_path,
                stopper=lambda name: events.append(f"stop:{name}") or {"exists": True},
                deleter=lambda name: events.append(f"delete:{name}") or {},
                image_setter=lambda name, image: events.append(f"image:{name}") or {},
                configuration_restorer=lambda name, **kwargs: events.append(f"config:{name}") or {},
                starter=lambda name: events.append(f"start:{name}") or {},
                fresh_cleanup=lambda: events.append("firewall-cleanup"),
            )

            self.assertEqual(
                events,
                [
                    "stop:HRMCentralService",
                    "image:HRMCentralService",
                    "config:HRMCentralService",
                    "start:HRMCentralService",
                ],
            )
            self.assertEqual(recovered["phase"], "recovered")
            self.assertFalse(recovered["committed"])

    def test_fresh_install_delete_failure_does_not_mark_recovered(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_path = Path(td) / "service-cutover-state.json"
            self._fresh_state(state_path)
            advance_service_cutover_journal(state_path, "service_stopped")
            advance_service_cutover_journal(state_path, "image_switched")

            def fail_delete(_name: str) -> dict[str, object]:
                raise RuntimeError("synthetic delete failure")

            with self.assertRaisesRegex(RuntimeError, "delete failure"):
                recover_windows_service_cutover(
                    state_path,
                    stopper=lambda _name: {"exists": True},
                    deleter=fail_delete,
                )

            persisted = load_service_cutover_journal(state_path)
            self.assertEqual(persisted["phase"], "image_switched")
            self.assertFalse(persisted["committed"])

    def test_coordinator_rolls_back_fresh_install_when_database_state_is_absent(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            service_state = root / "service-cutover-state.json"
            database_state = root / "installer-upgrade-state.json"
            self._fresh_state(service_state)
            service_calls: list[Path] = []

            result = recover_upgrade_transaction(
                service_state,
                database_state,
                restore_database=lambda _path: self.fail(
                    "database restore must not be called when state is absent"
                ),
                recover_service=lambda path: service_calls.append(path) or {
                    "phase": "recovered",
                    "committed": False,
                },
            )

            self.assertEqual(service_calls, [service_state.resolve()])
            self.assertEqual(result["decision"], "rollback")
            self.assertFalse(result["database_recovered"])
            self.assertTrue(result["service_recovered"])

    def test_coordinator_can_commit_fresh_install_without_database_upgrade_state(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            service_state = root / "service-cutover-state.json"
            database_state = root / "installer-upgrade-state.json"
            self._fresh_state(service_state)
            for phase in ("service_stopped", "image_switched", "service_started", "ready"):
                advance_service_cutover_journal(service_state, phase)

            result = commit_upgrade_transaction(
                service_state,
                database_state,
                commit_service=mark_service_cutover_committed,
                commit_database=lambda _path: self.fail(
                    "database commit must not be called when state is absent"
                ),
            )

            self.assertEqual(result["decision"], "commit")
            self.assertTrue(result["service_committed"])
            self.assertFalse(result["database_committed"])

    def test_schema1_cutover_journal_is_loaded_as_existing_service(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_path = Path(td) / "service-cutover-state.json"
            payload = {
                "schema": 1,
                "service_name": "HRMCentralService",
                "original_image_path": r'"C:\Program Files\SazmanHR Enterprise\ServiceRuntime\svc-old\HRMService.exe"',
                "original_executable": r"C:\Program Files\SazmanHR Enterprise\ServiceRuntime\svc-old\HRMService.exe",
                "original_start_type": 2,
                "original_object_name": r"NT AUTHORITY\LocalService",
                "original_sid_type": 1,
                "was_running": True,
                "target_executable": self._target(),
                "phase": "image_switched",
                "committed": False,
            }
            state_path.write_text(
                json.dumps(payload, indent=2, sort_keys=True),
                encoding="utf-8",
            )

            loaded = load_service_cutover_journal(state_path)

            self.assertTrue(loaded["service_existed_before"])
            self.assertEqual(loaded["original_executable"], payload["original_executable"])

    def test_existing_snapshot_defaults_to_existing_service_for_compatibility(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_path = Path(td) / "service-cutover-state.json"
            snapshot = {
                "service_name": "HRMCentralService",
                "original_image_path": r'"C:\Program Files\SazmanHR Enterprise\ServiceRuntime\svc-old\HRMService.exe"',
                "original_executable": r"C:\Program Files\SazmanHR Enterprise\ServiceRuntime\svc-old\HRMService.exe",
                "original_start_type": 2,
                "original_object_name": r"NT AUTHORITY\LocalService",
                "original_sid_type": 1,
                "was_running": True,
                "target_executable": self._target(),
            }

            created = create_service_cutover_journal(state_path, snapshot)

            self.assertTrue(created["service_existed_before"])


if __name__ == "__main__":
    unittest.main()
