from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sazmanhr.windows_service_control import (
    SERVICE_RUNNING,
    create_windows_service_cutover_journal,
    load_service_cutover_journal,
)


class Rc3ServiceCutoverJournalIntegrationTests(unittest.TestCase):
    def test_prepare_cutover_snapshots_live_service_configuration_before_stop(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_path = Path(td) / "service-cutover-state.json"
            target = r"C:\Program Files\SazmanHR Enterprise\ServiceRuntime\svc-new\HRMService.exe"

            def configuration_reader(service_name: str) -> dict[str, object]:
                self.assertEqual(service_name, "HRMCentralService")
                return {
                    "image_path": r'"C:\Program Files\SazmanHR Enterprise\ServiceRuntime\svc-old\HRMService.exe"',
                    "start_type": 2,
                    "object_name": r"NT AUTHORITY\LocalService",
                    "sid_type": 1,
                }

            def state_reader(service_name: str) -> int | None:
                self.assertEqual(service_name, "HRMCentralService")
                return SERVICE_RUNNING

            result = create_windows_service_cutover_journal(
                state_path,
                "HRMCentralService",
                target,
                configuration_reader=configuration_reader,
                state_reader=state_reader,
            )

            self.assertEqual(result["phase"], "snapshotted")
            self.assertFalse(result["committed"])
            self.assertTrue(result["was_running"])
            self.assertEqual(
                result["original_executable"],
                r"C:\Program Files\SazmanHR Enterprise\ServiceRuntime\svc-old\HRMService.exe",
            )
            self.assertEqual(result["original_start_type"], 2)
            self.assertEqual(
                result["original_object_name"],
                r"NT AUTHORITY\LocalService",
            )
            self.assertEqual(result["original_sid_type"], 1)
            self.assertEqual(result["target_executable"], target)
            self.assertEqual(load_service_cutover_journal(state_path), result)

    def test_prepare_cutover_fails_closed_if_service_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_path = Path(td) / "service-cutover-state.json"

            with self.assertRaisesRegex(RuntimeError, "does not exist"):
                create_windows_service_cutover_journal(
                    state_path,
                    "HRMCentralService",
                    r"C:\Program Files\SazmanHR Enterprise\ServiceRuntime\svc-new\HRMService.exe",
                    configuration_reader=lambda _name: {
                        "image_path": r'"C:\old.exe"',
                        "start_type": 2,
                        "object_name": r"NT AUTHORITY\LocalService",
                        "sid_type": 1,
                    },
                    state_reader=lambda _name: None,
                )

            self.assertFalse(state_path.exists())

    def test_prepare_cutover_rejects_malformed_live_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state_path = Path(td) / "service-cutover-state.json"

            with self.assertRaisesRegex(RuntimeError, "configuration"):
                create_windows_service_cutover_journal(
                    state_path,
                    "HRMCentralService",
                    r"C:\Program Files\SazmanHR Enterprise\ServiceRuntime\svc-new\HRMService.exe",
                    configuration_reader=lambda _name: {
                        "image_path": "",
                        "start_type": 2,
                        "object_name": r"NT AUTHORITY\LocalService",
                        "sid_type": 1,
                    },
                    state_reader=lambda _name: SERVICE_RUNNING,
                )

            self.assertFalse(state_path.exists())


if __name__ == "__main__":
    unittest.main()
