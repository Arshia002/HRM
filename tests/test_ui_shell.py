from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / "src" / "sazmanhr" / "client.py"
BRANDING = ROOT / "src" / "sazmanhr" / "branding.py"
CLIENT_SPEC = ROOT / "build" / "windows" / "client.spec"


class NativeUiShellTests(unittest.TestCase):
    def test_client_source_is_valid_python(self) -> None:
        ast.parse(CLIENT.read_text(encoding="utf-8"), filename=str(CLIENT))

    def test_native_v49_shell_markers_are_present(self) -> None:
        text = CLIENT.read_text(encoding="utf-8")
        for marker in (
            'setObjectName("brandPanel")',
            'setObjectName("loginPanel")',
            'setObjectName("topbar")',
            'setObjectName("connectionBadge")',
            'setMinimumSize(860, 520)',
            'setMinimumSize(1180, 700)',
            'QBoxLayout.Direction.RightToLeft',
            '"--ui-smoke-test"',
        ):
            self.assertIn(marker, text)

    def test_native_shell_has_no_webview(self) -> None:
        text = CLIENT.read_text(encoding="utf-8")
        self.assertNotIn("QtWebEngine", text)
        self.assertNotIn("QWebEngine", text)
        self.assertNotIn("WebView", text)

    def test_official_hrm_branding_is_bundled(self) -> None:
        branding = BRANDING.read_text(encoding="utf-8")
        spec = CLIENT_SPEC.read_text(encoding="utf-8")
        self.assertIn('APP_NAME = "HRM"', branding)
        self.assertIn('COMPANY_NAME = "شرکت توزیع نیروی برق استان کرمانشاه"', branding)
        self.assertIn('root / "assets" / "HRM.png"', spec)
        for relative in ("assets/HRM.png", "assets/HRM.ico", "assets/company-logo-source.png"):
            path = ROOT / relative
            self.assertTrue(path.is_file(), relative)
            self.assertGreater(path.stat().st_size, 100)

    def test_frozen_builder_runs_ui_smoke_before_installer(self) -> None:
        builder = (ROOT / "build" / "windows" / "build_windows.py").read_text(encoding="utf-8")
        ui_smoke = builder.index('"--ui-smoke-test"')
        inno = builder.index('iscc = install_inno(log)')
        self.assertLess(ui_smoke, inno)


if __name__ == "__main__":
    unittest.main()
