from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SMOKE = ROOT / "build" / "windows" / "smoke-install.ps1"

LEGACY_SERVICES = (
    "SazmanHREnterpriseCentral",
    "SazmanHRCentral",
    "SazmanHRNetworkServer",
)


class Rc3LegacySmokeContractTests(unittest.TestCase):
    def test_smoke_refuses_to_overwrite_real_legacy_services(self) -> None:
        text = SMOKE.read_text(encoding="utf-8").lower()
        self.assertIn("assert-nopreexistinglegacyservices", text)
        self.assertIn("refusing to create smoke fixture", text)
        self.assertIn("skipping cleanup for non-fixture legacy service", text)
        self.assertIn("pathName".lower(), text)
        for name in LEGACY_SERVICES:
            self.assertIn(name.lower(), text)

    def test_smoke_creates_stopped_auto_start_fixture_and_requires_disabled_after_upgrade(self) -> None:
        text = SMOKE.read_text(encoding="utf-8").lower()
        self.assertIn("new-testlegacyservices", text)
        self.assertIn("start= auto", text)
        self.assertIn("state -ne 'stopped'", text)
        self.assertIn("startmode -ne 'auto'", text)
        self.assertIn("assert-legacyservicesdisabled", text)
        self.assertIn("startmode -ne 'disabled'", text)
        self.assertIn("legacy-service-stop-before-copy-", text)
        self.assertIn("legacy-service-disable-before-copy-", text)
        self.assertIn("assert-legacymigrationloggedbeforecopy", text)

    def test_smoke_requires_exactly_one_canonical_port_owner(self) -> None:
        text = SMOKE.read_text(encoding="utf-8").lower()
        self.assertIn("assert-canonicalportowner", text)
        self.assertIn("get-nettcpconnection", text)
        self.assertIn("owningprocess", text)
        self.assertIn("processid", text)
        self.assertIn("hrmcentralservice", text)
        self.assertIn("legacy-service-state.json", text)
        self.assertIn("remove-testlegacyfixtures", text)


if __name__ == "__main__":
    unittest.main()
