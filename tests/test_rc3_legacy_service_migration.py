from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "build" / "windows" / "HRM.iss"

LEGACY_SERVICES = (
    "SazmanHREnterpriseCentral",
    "SazmanHRCentral",
    "SazmanHRNetworkServer",
)


class Rc3LegacyServiceMigrationTests(unittest.TestCase):
    def test_installer_recognizes_all_known_legacy_services(self) -> None:
        text = INSTALLER.read_text(encoding="utf-8")
        for name in LEGACY_SERVICES:
            self.assertIn(name, text)

    def test_legacy_services_are_stopped_before_disable_and_never_deleted(self) -> None:
        text = INSTALLER.read_text(encoding="utf-8").lower()
        self.assertIn("legacy-service-stop-before-copy-", text)
        self.assertIn("legacy-service-disable-before-copy-", text)
        self.assertIn("start= disabled", text)
        self.assertLess(
            text.index("legacy-service-stop-before-copy-"),
            text.index("legacy-service-disable-before-copy-"),
        )
        for name in LEGACY_SERVICES:
            self.assertNotIn("delete " + name.lower(), text)

    def test_failure_rollback_and_success_validation_are_explicit(self) -> None:
        text = INSTALLER.read_text(encoding="utf-8").lower()
        self.assertIn("restorelegacyservicesifneeded", text)
        self.assertIn("restoreonelegacyservice", text)
        self.assertIn("verifylegacyservicesdisabled", text)
        self.assertIn("legacy-service-final-validation-", text)
        self.assertIn("currentstarttype <> 4", text)
        self.assertIn("starttype <> 4", text)


if __name__ == "__main__":
    unittest.main()
