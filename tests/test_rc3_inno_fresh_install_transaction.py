from __future__ import annotations

import unittest
from pathlib import Path


class Rc3InnoFreshInstallTransactionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.script = Path("build/windows/HRM.iss").read_text(encoding="utf-8")
        start = cls.script.index("procedure ProvisionEnterpriseServer;")
        end = cls.script.index("procedure InitializeWizard;", start)
        cls.provision = cls.script[start:end]

    def test_service_existence_detection_uses_scm_not_registry(self) -> None:
        prepare_start = self.script.index("function PrepareToInstall(var NeedsRestart: Boolean): String;")
        prepare_end = self.script.index("function GetCustomSetupExitCode: Integer;", prepare_start)
        prepare = self.script[prepare_start:prepare_end]

        self.assertNotIn(
            "ServiceExistedBeforeInstall := RegKeyExists",
            prepare,
        )
        self.assertIn(
            "ServiceExistedBeforeInstall := ServiceExistsInScm('HRMCentralService')",
            prepare,
        )
        self.assertIn(
            "function ServiceExistsInScm(ServiceName: String): Boolean;",
            self.script,
        )
        self.assertIn(
            "else if ResultCode = 1060 then",
            self.script,
        )
        self.assertIn(
            "RaiseException('SCM query failed for service ' + ServiceName +",
            self.script,
        )

    def test_fresh_install_prepares_durable_journal_before_service_creation(self) -> None:
        prepare = self.provision.index("--prepare-service-install HRMCentralService")
        install = self.provision.index("--startup auto install")
        self.assertLess(prepare, install)
        self.assertIn("--service-cutover-state-file", self.provision)
        self.assertIn("--service-image-executable", self.provision)

    def test_existing_and_fresh_paths_share_the_persistent_service_journal(self) -> None:
        self.assertIn("--prepare-service-cutover HRMCentralService", self.provision)
        self.assertIn("--prepare-service-install HRMCentralService", self.provision)
        self.assertGreaterEqual(
            self.provision.count("ServiceCutoverStatePath"),
            6,
        )
        self.assertNotIn("DeleteFile(ServiceCutoverStatePath)", self.provision)

    def test_fresh_install_enters_shared_phase_machine_before_database_work(self) -> None:
        prepare = self.provision.index("--prepare-service-install HRMCentralService")
        install = self.provision.index("--startup auto install")
        db_upgrade = self.provision.index("--upgrade-legacy-database")
        first_stopped_after_prepare = self.provision.index(
            "--advance-service-cutover service_stopped",
            prepare,
        )
        image_switched_after_install = self.provision.index(
            "--advance-service-cutover image_switched",
            install,
        )

        self.assertLess(prepare, first_stopped_after_prepare)
        self.assertLess(first_stopped_after_prepare, db_upgrade)
        self.assertLess(db_upgrade, install)
        self.assertLess(install, image_switched_after_install)


if __name__ == "__main__":
    unittest.main()
