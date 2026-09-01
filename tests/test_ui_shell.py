from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / "src" / "sazmanhr" / "client.py"
V49_PAGES = ROOT / "src" / "sazmanhr" / "ui_v49.py"
BRANDING = ROOT / "src" / "sazmanhr" / "branding.py"
CLIENT_SPEC = ROOT / "build" / "windows" / "client.spec"


class NativeUiShellTests(unittest.TestCase):
    def test_client_source_is_valid_python(self) -> None:
        ast.parse(CLIENT.read_text(encoding="utf-8"), filename=str(CLIENT))
        ast.parse(V49_PAGES.read_text(encoding="utf-8"), filename=str(V49_PAGES))

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
        text = CLIENT.read_text(encoding="utf-8") + V49_PAGES.read_text(encoding="utf-8")
        self.assertNotIn("QtWebEngine", text)
        self.assertNotIn("QWebEngine", text)
        self.assertNotIn("WebView", text)

    def test_all_v49_reference_pages_are_native_and_smoke_refreshed(self) -> None:
        client = CLIENT.read_text(encoding="utf-8")
        pages = V49_PAGES.read_text(encoding="utf-8")
        for marker in (
            '"formalChart"', '"statusChart"', '"personnelDirectory"',
            '"personnelEducation"', '"jobFamilies"', '"personnelAge"',
            '"reports"', '"imports"', '"users"', '"history"',
            '"systemHealth"', '"settings"',
        ):
            self.assertIn(marker, client + pages)
        for page_class in (
            "StatusChartPage", "PersonnelEducationPage", "PersonnelStatusPage",
            "PersonnelAgePage", "ReportsPage", "ImportPage", "UsersPage",
            "HistoryBackupPage", "SystemHealthPage", "SettingsPage",
        ):
            self.assertIn(f"class {page_class}", pages)
            self.assertIn(f"{page_class}(self)", client)
        self.assertIn("for index in range(window.nav.count())", client)
        self.assertIn("set(V49_REFERENCE_PAGES) - set(window.page_keys)", client)

    def test_v49_analytics_and_import_pages_use_real_service_contracts(self) -> None:
        pages = V49_PAGES.read_text(encoding="utf-8")
        self.assertIn('self.call("GET", "/api/analytics")', pages)
        self.assertIn('self.call("GET", "/api/migration/status")', pages)
        self.assertIn('"--expected-personnel"', pages)
        self.assertIn('"--expected-fixed", "536"', pages)
        self.assertIn('"--expected-named", "32"', pages)
        self.assertNotIn("--apply-to-db", pages)

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
