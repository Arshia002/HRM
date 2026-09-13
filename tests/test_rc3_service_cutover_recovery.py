from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sazmanhr.windows_service_control import (
    advance_service_cutover_journal,
    create_service_cutover_journal,
    load_service_cutover_journal,
    mark_service_cutover_committed,
    recover_windows_service_cutover,
)


class Rc3ServiceCutoverRecoveryTests(unittest.TestCase):
    def _snapshot(self, *, was_running: bool = True) -> dict[str, object]:
        return {
            "service_name": "HRMCentralService",
            "original_image_path": r'"C:\Program Files\SazmanHR Enterprise\ServiceRuntime\svc-old\HRMService.exe"',
            "original_executable": r"C:\Program Files\SazmanHR Enterprise\ServiceRuntime\svc-old\HRMService.exe",
            "original_start_type": 2,
            "original_object_name": r"NT AUTHORITY\LocalService",
            "original_sid_type": 1,
            "was_running": was_running,
            "target_executable": r"C:\Program Files\SazmanHR Enterprise\ServiceRuntime\svc-new\HRMService.exe",
        }

    def _journal_at_phase(self, state_path: Path, phase: str, *, was_running: bool = True) -> None:
        create_service_cutover_journal(state_path, self._snapshot(was_running=was_running))
        phases = ("service_stopped", "image_switched", "service_started", "ready")
        for candidate in phases:
            if phase == "snapshotted":
                break
            advance_service_cutover_journal(state_path, candidate)
            if candidate == phase:
                break

    def test_recovery_restores_original_service_and_running_state(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_path = Path(td) / "service-cutover-state.json"
            self._journal_at_phase(state_path, "image_switched", was_running=True)
            events: list[object] = []

            def stopper(name: str) -> dict[str, object]:
                events.append(("stop", name))
                return {"exists": True}

            def image_setter(name: str, executable: str | Path) -> dict[str, object]:
                events.append(("image", name, str(executable)))
                return {"exists": True}

            def configuration_restorer(
                name: str,
                *,
                start_type: int,
                object_name: str,
                sid_type: int,
            ) -> dict[str, object]:
                events.append(("config", name, start_type, object_name, sid_type))
                return {"ok": True}

            def starter(name: str) -> dict[str, object]:
                events.append(("start", name))
                return {"exists": True}

            result = recover_windows_service_cutover(
                state_path,
                stopper=stopper,
                image_setter=image_setter,
                configuration_restorer=configuration_restorer,
                starter=starter,
            )

            self.assertEqual(
                events,
                [
                    ("stop", "HRMCentralService"),
                    (
                        "image",
                        "HRMCentralService",
                        r"C:\Program Files\SazmanHR Enterprise\ServiceRuntime\svc-old\HRMService.exe",
                    ),
                    (
                        "config",
                        "HRMCentralService",
                        2,
                        r"NT AUTHORITY\LocalService",
                        1,
                    ),
                    ("start", "HRMCentralService"),
                ],
            )
            self.assertEqual(result["phase"], "recovered")
            self.assertFalse(result["committed"])
            self.assertEqual(load_service_cutover_journal(state_path)["phase"], "recovered")

    def test_recovery_preserves_original_stopped_state(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_path = Path(td) / "service-cutover-state.json"
            self._journal_at_phase(state_path, "service_stopped", was_running=False)
            started: list[str] = []

            result = recover_windows_service_cutover(
                state_path,
                stopper=lambda _name: {"exists": True},
                image_setter=lambda _name, _exe: {"exists": True},
                configuration_restorer=lambda _name, **_kwargs: {"ok": True},
                starter=lambda name: started.append(name) or {"exists": True},
            )

            self.assertEqual(started, [])
            self.assertEqual(result["phase"], "recovered")

    def test_committed_journal_is_a_noop(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_path = Path(td) / "service-cutover-state.json"
            self._journal_at_phase(state_path, "ready")
            mark_service_cutover_committed(state_path)
            events: list[str] = []

            result = recover_windows_service_cutover(
                state_path,
                stopper=lambda _name: events.append("stop") or {"exists": True},
                image_setter=lambda _name, _exe: events.append("image") or {"exists": True},
                configuration_restorer=lambda _name, **_kwargs: events.append("config") or {"ok": True},
                starter=lambda _name: events.append("start") or {"exists": True},
            )

            self.assertEqual(events, [])
            self.assertEqual(result["phase"], "committed")
            self.assertTrue(result["committed"])

    def test_failed_recovery_does_not_mark_journal_recovered(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_path = Path(td) / "service-cutover-state.json"
            self._journal_at_phase(state_path, "image_switched")

            def fail_image(_name: str, _exe: str | Path) -> dict[str, object]:
                raise RuntimeError("synthetic image restore failure")

            with self.assertRaisesRegex(RuntimeError, "synthetic image restore failure"):
                recover_windows_service_cutover(
                    state_path,
                    stopper=lambda _name: {"exists": True},
                    image_setter=fail_image,
                    configuration_restorer=lambda _name, **_kwargs: {"ok": True},
                    starter=lambda _name: {"exists": True},
                )

            state = load_service_cutover_journal(state_path)
            self.assertEqual(state["phase"], "image_switched")
            self.assertFalse(state["committed"])

    def test_recovered_journal_can_be_replaced_by_next_transaction(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_path = Path(td) / "service-cutover-state.json"
            self._journal_at_phase(state_path, "snapshotted")

            recovered = recover_windows_service_cutover(
                state_path,
                stopper=lambda _name: {"exists": True},
                image_setter=lambda _name, _exe: {"exists": True},
                configuration_restorer=lambda _name, **_kwargs: {"ok": True},
                starter=lambda _name: {"exists": True},
            )
            self.assertEqual(recovered["phase"], "recovered")

            replacement = create_service_cutover_journal(state_path, self._snapshot())
            self.assertEqual(replacement["phase"], "snapshotted")
            self.assertFalse(replacement["committed"])


if __name__ == "__main__":
    unittest.main()
