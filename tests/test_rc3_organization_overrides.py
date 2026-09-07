from __future__ import annotations

import hashlib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
APP = WEB / "assets" / "app.js"
AUTH = WEB / "assets" / "modules" / "auth-shell.js"
OVERRIDE = WEB / "assets" / "modules" / "organization-overrides.js"
INSTALLER = ROOT / "build" / "windows" / "HRM.iss"
REFERENCE_APP_SHA256 = "d65eebcb8e807effe84c856e35c7a96778773cbb7ea33e753a997e8adf4d9070"


class Rc3OrganizationOverridesTests(unittest.TestCase):
    def test_reference_app_bundle_remains_immutable(self) -> None:
        self.assertEqual(hashlib.sha256(APP.read_bytes()).hexdigest(), REFERENCE_APP_SHA256)

    def test_organization_override_is_loaded_after_reference_app(self) -> None:
        auth = AUTH.read_text(encoding="utf-8")
        self.assertIn("assets/modules/organization-overrides.js", auth)
        self.assertGreater(auth.index("organization-overrides.js"), auth.index("enterprise-bridge.js"))

    def test_reports_inspection_kpi_is_visually_removed_by_action_contract(self) -> None:
        text = OVERRIDE.read_text(encoding="utf-8")
        self.assertIn('[data-org450-action="issue"]', text)
        self.assertIn("card.hidden=true", text)
        self.assertIn("card.disabled=true", text)
        self.assertIn("display','none','important", text)
        self.assertIn("MutationObserver", text)
        # Keep the canonical app's 10-node QA contract intact; hide only in the UI layer.
        self.assertNotIn("card.remove()", text)
        # Do not key the customization to a Persian label; action contract is more stable.
        self.assertNotIn("نیازمند بررسی", text)
        self.assertNotIn("نیازمند بازرسی", text)



    def test_publisher_is_visible_in_settings_via_override_layer(self) -> None:
        text = OVERRIDE.read_text(encoding="utf-8")
        self.assertIn("const PUBLISHER_FA='ارشیا شهبازی';", text)
        self.assertIn("const PUBLISHER_EN='Arshia Shahbazi';", text)
        self.assertIn("#page-settings .info-list", text)
        self.assertIn("data-rc3-publisher", text)
        self.assertIn("label.textContent='ناشر'", text)
        self.assertIn("value.textContent=PUBLISHER_FA", text)

    def test_installer_metadata_names_publisher_without_code_signing_requirement(self) -> None:
        text = INSTALLER.read_text(encoding="utf-8")
        self.assertIn("AppPublisher=Arshia Shahbazi", text)

if __name__ == "__main__":
    unittest.main()
