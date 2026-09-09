from __future__ import annotations

import unittest
from pathlib import Path

from sazmanhr.windows_service_control import (
    SERVICE_RUNNING,
    SERVICE_START_PENDING,
    SERVICE_STOPPED,
    start_windows_service,
)

ROOT = Path(__file__).resolve().parents[1]


def state_output(state: int) -> str:
    return f"STATE              : {state}  TEST_STATE\n"


class Rc3WindowsServiceHostContractTests(unittest.TestCase):
    def test_service_spec_is_onedir_not_onefile(self) -> None:
        spec = (ROOT / "build" / "windows" / "service.spec").read_text(encoding="utf-8")
        self.assertIn("exclude_binaries=True", spec)
        self.assertIn("COLLECT(", spec)
        self.assertNotIn("pyz, a.scripts, a.binaries, a.datas, []", spec)

    def test_builder_and_inno_stage_onedir_to_versioned_runtime_path(self) -> None:
        builder = (ROOT / "build" / "windows" / "build_windows.py").read_text(encoding="utf-8")
        installer = (ROOT / "build" / "windows" / "HRM.iss").read_text(encoding="utf-8")
        self.assertIn('("service.spec", "HRMService/HRMService.exe")', builder)
        self.assertIn(
            'f"/DServiceRuntimeGeneration={service_runtime_generation}"',
            builder,
        )
        self.assertIn(
            'Source: "{#DistDir}\\HRMService\\*"; DestDir: "{app}\\ServiceRuntime\\{#ServiceRuntimeGeneration}"',
            installer,
        )
        self.assertNotIn(
            'Source: "{#DistDir}\\HRMService\\*"; DestDir: "{app}\\Server"',
            installer,
        )
    def test_installer_uses_verified_controller_for_provisioning_start_stop(self) -> None:
        installer = (ROOT / "build" / "windows" / "HRM.iss").read_text(encoding="utf-8")
        provision = installer[
            installer.index("procedure ProvisionEnterpriseServer;"):
            installer.index("procedure InitializeWizard;")
        ]
        self.assertGreaterEqual(provision.count("--start-windows-service HRMCentralService"), 2)
        self.assertGreaterEqual(provision.count("--stop-windows-service HRMCentralService"), 2)
        self.assertNotIn("--wait 30 start", provision)
        self.assertNotIn("--wait 30 stop", provision)

    def test_rollback_restart_uses_preflight_controller(self) -> None:
        installer = (ROOT / "build" / "windows" / "HRM.iss").read_text(encoding="utf-8")
        restore = installer[
            installer.index("procedure RestoreOriginalServiceIfNeeded;"):
            installer.index("procedure RecoverServerAfterFailure;")
        ]
        self.assertIn("{tmp}\\HRMServerPreflight.exe", restore)
        self.assertIn("--start-windows-service HRMCentralService", restore)
        self.assertNotIn("--wait 30 start", restore)

    def test_start_helper_waits_until_scm_reports_running(self) -> None:
        states = iter((SERVICE_STOPPED, SERVICE_START_PENDING, SERVICE_RUNNING))
        calls: list[tuple[str, str]] = []

        def runner(action: str, name: str) -> tuple[int, str]:
            calls.append((action, name))
            if action == "queryex":
                return 0, state_output(next(states))
            if action == "start":
                return 0, "START_PENDING"
            raise AssertionError(action)

        result = start_windows_service(
            "HRMCentralService", runner=runner, sleeper=lambda _: None
        )
        self.assertEqual(result["final_state"], SERVICE_RUNNING)
        self.assertEqual(calls.count(("start", "HRMCentralService")), 1)

    def test_start_helper_fails_if_service_returns_to_stopped(self) -> None:
        states = iter((SERVICE_STOPPED, SERVICE_STOPPED))

        def runner(action: str, name: str) -> tuple[int, str]:
            if action == "queryex":
                return 0, state_output(next(states))
            if action == "start":
                return 0, "START_PENDING"
            raise AssertionError(action)

        with self.assertRaisesRegex(RuntimeError, "stopped before reaching RUNNING"):
            start_windows_service(
                "HRMCentralService", runner=runner, sleeper=lambda _: None
            )

    def test_start_helper_fails_closed_on_timeout(self) -> None:
        clock_values = iter((0.0, 2.0))

        def runner(action: str, name: str) -> tuple[int, str]:
            if action == "queryex":
                return 0, state_output(SERVICE_START_PENDING)
            raise AssertionError(action)

        with self.assertRaisesRegex(TimeoutError, "did not reach RUNNING"):
            start_windows_service(
                "HRMCentralService",
                timeout_seconds=1,
                runner=runner,
                clock=lambda: next(clock_values),
                sleeper=lambda _: None,
            )


if __name__ == "__main__":
    unittest.main()
