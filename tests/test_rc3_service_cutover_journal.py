from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from sazmanhr.windows_service_control import (
    SERVICE_CUTOVER_JOURNAL_SCHEMA,
    advance_service_cutover_journal,
    create_service_cutover_journal,
    load_service_cutover_journal,
    mark_service_cutover_committed,
)


class Rc3ServiceCutoverJournalTests(unittest.TestCase):
    def _snapshot(self) -> dict[str, object]:
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

    def test_create_persists_complete_uncommitted_snapshot_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_path = Path(td) / "service-cutover-state.json"
            result = create_service_cutover_journal(state_path, self._snapshot())

            self.assertTrue(state_path.is_file())
            self.assertFalse(state_path.with_suffix(state_path.suffix + ".staged").exists())
            self.assertEqual(result["schema"], SERVICE_CUTOVER_JOURNAL_SCHEMA)
            self.assertEqual(result["phase"], "snapshotted")
            self.assertFalse(result["committed"])

            loaded = load_service_cutover_journal(state_path)
            self.assertEqual(loaded, result)
            for key, value in self._snapshot().items():
                self.assertEqual(loaded[key], value)

    def test_existing_uncommitted_journal_cannot_be_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_path = Path(td) / "service-cutover-state.json"
            create_service_cutover_journal(state_path, self._snapshot())

            with self.assertRaisesRegex(RuntimeError, "uncommitted"):
                create_service_cutover_journal(state_path, self._snapshot())

            loaded = load_service_cutover_journal(state_path)
            self.assertEqual(loaded["phase"], "snapshotted")
            self.assertFalse(loaded["committed"])

    def test_phase_progression_is_monotonic_and_durable(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_path = Path(td) / "service-cutover-state.json"
            create_service_cutover_journal(state_path, self._snapshot())

            for phase in ("service_stopped", "image_switched", "service_started", "ready"):
                state = advance_service_cutover_journal(state_path, phase)
                self.assertEqual(state["phase"], phase)
                self.assertEqual(load_service_cutover_journal(state_path)["phase"], phase)

            with self.assertRaisesRegex(RuntimeError, "transition"):
                advance_service_cutover_journal(state_path, "image_switched")

            self.assertEqual(load_service_cutover_journal(state_path)["phase"], "ready")

    def test_commit_is_durable_and_preserves_original_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_path = Path(td) / "service-cutover-state.json"
            original = create_service_cutover_journal(state_path, self._snapshot())
            for phase in ("service_stopped", "image_switched", "service_started", "ready"):
                advance_service_cutover_journal(state_path, phase)

            committed = mark_service_cutover_committed(state_path)
            self.assertTrue(committed["committed"])
            self.assertEqual(committed["phase"], "committed")
            for key in self._snapshot():
                self.assertEqual(committed[key], original[key])

            reloaded = load_service_cutover_journal(state_path)
            self.assertTrue(reloaded["committed"])
            self.assertEqual(reloaded["phase"], "committed")

    def test_corrupt_or_incomplete_journal_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_path = Path(td) / "service-cutover-state.json"

            state_path.write_text("{not-json", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "invalid"):
                load_service_cutover_journal(state_path)

            incomplete = {
                "schema": SERVICE_CUTOVER_JOURNAL_SCHEMA,
                "service_name": "HRMCentralService",
                "phase": "snapshotted",
                "committed": False,
            }
            state_path.write_text(json.dumps(incomplete), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "incomplete"):
                load_service_cutover_journal(state_path)


if __name__ == "__main__":
    unittest.main()
