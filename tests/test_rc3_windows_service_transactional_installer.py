from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Rc3WindowsServiceTransactionalInstallerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.installer = (ROOT / "build" / "windows" / "HRM.iss").read_text(encoding="utf-8")
        self.builder = (ROOT / "build" / "windows" / "build_windows.py").read_text(encoding="utf-8")

    def test_service_runtime_is_versioned_and_never_copied_over_canonical_exe(self) -> None:
        self.assertIn(
            'Source: "{#DistDir}\\HRMService\\*"; DestDir: "{app}\\ServiceRuntime\\{#ServiceRuntimeGeneration}"',
            self.installer,
        )
        self.assertIn("onlyifdoesntexist", self.installer)
        self.assertNotIn(
            'Source: "{#DistDir}\\HRMService\\*"; DestDir: "{app}\\Server"',
            self.installer,
        )
        self.assertNotIn('{app}\\Server\\HRMService.exe', self.installer)

    def test_builder_passes_content_addressed_generation_to_inno(self) -> None:
        self.assertIn(
            'service_runtime_generation = f"svc-{runtime_digest[:24]}"',
            self.builder,
        )
        self.assertIn(
            'f"/DServiceRuntimeGeneration={service_runtime_generation}"',
            self.builder,
        )

    def test_pre_copy_phase_snapshots_but_does_not_stop_canonical_service(self) -> None:
        prepare = self.installer[
            self.installer.index("function PrepareToInstall"):
            self.installer.index("function GetCustomSetupExitCode")
        ]
        self.assertIn("SnapshotOriginalServiceConfiguration", prepare)
        self.assertIn("service-snapshot-image-missing", self.installer)
        self.assertIn("server-preflight-isolated", prepare)
        self.assertNotIn("--stop-windows-service HRMCentralService", prepare)

    def test_post_copy_cutover_order_is_verify_stop_switch_health_ready(self) -> None:
        provision = self.installer[
            self.installer.index("procedure ProvisionEnterpriseServer;"):
            self.installer.index("procedure InitializeWizard;")
        ]
        markers = [
            "--verify-service-runtime",
            "service-stop-for-cutover",
            "--set-windows-service-image HRMCentralService",
            "--start-windows-service HRMCentralService",
            "--health-check https://127.0.0.1:8765",
            "service-runtime-transaction-ready",
        ]
        positions = [provision.index(marker) for marker in markers]
        self.assertEqual(positions, sorted(positions))

    def test_rollback_restores_old_image_and_health_checks_before_success(self) -> None:
        restore = self.installer[
            self.installer.index("procedure RestoreOriginalServiceIfNeeded;"):
            self.installer.index("procedure RecoverServerAfterFailure;")
        ]
        self.assertIn("--set-windows-service-image HRMCentralService", restore)
        self.assertIn("--start-windows-service HRMCentralService", restore)
        self.assertIn("--health-check https://127.0.0.1:8765", restore)
        self.assertIn("restore-original-service-image", restore)
        self.assertIn("restore-original-service-health", restore)

    def test_commit_occurs_only_at_ssdone(self) -> None:
        provision = self.installer[
            self.installer.index("procedure ProvisionEnterpriseServer;"):
            self.installer.index("procedure InitializeWizard;")
        ]
        curstep = self.installer[
            self.installer.index("procedure CurStepChanged"):
            self.installer.index("procedure DeinitializeSetup")
        ]
        self.assertIn("service-runtime-transaction-ready", provision)
        self.assertNotIn("service-runtime-transaction-commit", provision)
        self.assertIn("CurStep = ssDone", curstep)
        self.assertIn("service-runtime-transaction-commit", curstep)

    def test_uninstall_uses_controller_not_active_service_binary(self) -> None:
        uninstall = self.installer[
            self.installer.index("[UninstallRun]"):
            self.installer.index("[Code]")
        ]
        self.assertIn("{app}\\Server\\HRMServer.exe", uninstall)
        self.assertIn("--stop-windows-service HRMCentralService", uninstall)
        self.assertIn("--delete-windows-service HRMCentralService", uninstall)
        self.assertNotIn("HRMService.exe", uninstall)


if __name__ == "__main__":
    unittest.main()
