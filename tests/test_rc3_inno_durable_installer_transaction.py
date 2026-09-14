from __future__ import annotations

import unittest
from pathlib import Path


class Rc3InnoDurableInstallerTransactionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.script = Path("build/windows/HRM.iss").read_text(encoding="utf-8")

    def _section(self, start: str, end: str) -> str:
        a = self.script.index(start)
        b = self.script.index(end, a)
        return self.script[a:b]

    def test_service_cutover_journal_uses_persistent_programdata_path(self) -> None:
        self.assertIn("ServiceCutoverStatePath: String;", self.script)
        self.assertIn(
            r"ServiceCutoverStatePath := DataDir + '\backups\upgrade-transactions\service-cutover-state.json';",
            self.script,
        )
        self.assertNotIn(
            r"ServiceCutoverStatePath := ExpandConstant('{tmp}",
            self.script,
        )

    def test_prepare_to_install_recovers_previous_transaction_before_new_snapshot(self) -> None:
        section = self._section(
            "function PrepareToInstall(var NeedsRestart: Boolean): String;",
            "function GetCustomSetupExitCode: Integer;",
        )
        recover = section.index("--recover-installer-upgrade")
        snapshot = section.index("SnapshotOriginalServiceConfiguration(Result)")
        self.assertLess(recover, snapshot)
        self.assertIn("--service-cutover-state-file", section)
        self.assertIn("--database-upgrade-state-file", section)

    def test_existing_service_is_journaled_before_stop_and_each_cutover_phase_is_durable(self) -> None:
        section = self._section(
            "procedure ProvisionEnterpriseServer;",
            "procedure InitializeWizard;",
        )

        prepare = section.index("--prepare-service-cutover HRMCentralService")
        stop = section.index("--stop-windows-service HRMCentralService")
        stopped = section.index("--advance-service-cutover service_stopped")
        db_upgrade = section.index("--upgrade-legacy-database")
        image_switch = section.index("--set-windows-service-image HRMCentralService")
        image_switched = section.index("--advance-service-cutover image_switched")
        service_start = section.index("--start-windows-service HRMCentralService")
        service_started = section.index("--advance-service-cutover service_started")
        final_health_stage = section.index("'آزمون نهایی TLS و سرویس پس از سخت‌سازی ACL'")
        ready = section.index("--advance-service-cutover ready")

        self.assertLess(prepare, stop)
        self.assertLess(stop, stopped)
        self.assertLess(stopped, db_upgrade)
        self.assertLess(db_upgrade, image_switch)
        self.assertLess(image_switch, image_switched)
        self.assertLess(image_switched, service_start)
        self.assertLess(service_start, service_started)
        self.assertLess(service_started, final_health_stage)
        self.assertLess(final_health_stage, ready)

        self.assertIn("--service-cutover-state-file", section)
        self.assertIn("--service-image-executable", section)

    def test_failure_recovery_uses_persistent_transaction_coordinator(self) -> None:
        section = self._section(
            "procedure RecoverServerAfterFailure;",
            "procedure VerifyOneLegacyServiceDisabled",
        )
        self.assertIn("--recover-installer-upgrade", section)
        self.assertIn("--service-cutover-state-file", section)
        self.assertIn("--database-upgrade-state-file", section)

    def test_ssdone_commits_only_through_installer_transaction_coordinator(self) -> None:
        section = self._section(
            "procedure CurStepChanged(CurStep: TSetupStep);",
            "procedure DeinitializeSetup;",
        )
        self.assertIn("--commit-installer-upgrade", section)
        self.assertIn("--service-cutover-state-file", section)
        self.assertIn("--database-upgrade-state-file", section)
        self.assertNotIn("--commit-service-cutover", section)
        self.assertNotIn("--commit-legacy-database-upgrade", section)

        coordinator_commit = section.index("--commit-installer-upgrade")
        memory_commit = section.index("ServiceTransactionCommitted := True;")
        self.assertLess(coordinator_commit, memory_commit)

    def test_deinitialize_uses_persistent_recovery_before_memory_fallback(self) -> None:
        section = self.script[self.script.index("procedure DeinitializeSetup;") :]
        self.assertIn("--recover-installer-upgrade", section)
        coordinator_recovery = section.index("--recover-installer-upgrade")
        memory_fallback = section.index("RestoreOriginalServiceIfNeeded")
        self.assertLess(coordinator_recovery, memory_fallback)


if __name__ == "__main__":
    unittest.main()
