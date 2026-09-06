from __future__ import annotations

import ast
import hashlib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / "src" / "sazmanhr" / "client.py"
CLIENT_SPEC = ROOT / "build" / "windows" / "client.spec"
WEB = ROOT / "web"

REFERENCE_HASHES = {
    "index.html": "3e44e10bf0cea1ccee018bcda50035101ff956a4102a2887d01422695adad3cf",
    "assets/styles.css": "86f3c46e45200a475862f1e609791d59624d2542c22fa9ba9d5ad366a03182ba",
    "assets/app.js": "d65eebcb8e807effe84c856e35c7a96778773cbb7ea33e753a997e8adf4d9070",
    "assets/logo.svg": "078ed95b4afa50d3dfc14b49d8c34b6a6f99d84fc8894acc2cc9e0ecc20e7adf",
    "assets/login-power-final.webp": "06f5165bca158ddc61c715aaa7df9070ba8ab72e2742796110e1fc0bcd8966f1",
}
PAGES = (
    "formalChart", "statusChart", "personnelDirectory", "personnelEducation",
    "jobFamilies", "personnelAge", "reports", "imports", "users", "history",
    "systemHealth", "settings",
)


class ExactV49WebShellTests(unittest.TestCase):
    def test_client_source_is_valid_python(self) -> None:
        ast.parse(CLIENT.read_text(encoding="utf-8"), filename=str(CLIENT))

    def test_windows_shell_is_embedded_qtwebengine_and_pinned_preflight(self) -> None:
        text = CLIENT.read_text(encoding="utf-8")
        for marker in (
            "QWebEngineView", "QWebEnginePage", "PinnedPage", "ApiClient(",
            "tls_fingerprint=self.config.tls_fingerprint", "certificateError",
            '"--ui-smoke-test"', "REFERENCE_PAGE_IDS",
        ):
            self.assertIn(marker, text)
        self.assertNotIn("class LoginDialog", text)
        self.assertNotIn("class MainWindow", text)

    def test_exact_reference_visual_payload_is_hash_locked(self) -> None:
        for relative, expected in REFERENCE_HASHES.items():
            raw = (WEB / relative).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), expected, relative)

    def test_all_reference_pages_exist_in_exact_html(self) -> None:
        html = (WEB / "index.html").read_text(encoding="utf-8")
        for page in PAGES:
            self.assertIn(page, html)
        styles = (WEB / "assets" / "styles.css").read_text(encoding="utf-8")
        self.assertIn("login-power-final.webp", styles)
        self.assertIn("assets/styles.css", html)
        self.assertIn("assets/modules/auth-shell.js", html)

    def test_enterprise_bridge_is_loaded_without_rewriting_reference_app(self) -> None:
        html = (WEB / "index.html").read_text(encoding="utf-8")
        bridge = (WEB / "assets" / "modules" / "enterprise-bridge.js").read_text(encoding="utf-8")
        auth = (WEB / "assets" / "modules" / "auth-shell.js").read_text(encoding="utf-8")
        self.assertIn("enterprise-bridge.js", auth)
        self.assertIn("monthlyImport:true", bridge)
        self.assertIn("binaryBackup:true", bridge)
        self.assertIn("ownerRestore:true", bridge)
        self.assertIn("must_change_password", auth)

    def test_client_spec_bundles_web_and_qtwebengine(self) -> None:
        spec = CLIENT_SPEC.read_text(encoding="utf-8")
        self.assertIn('str(root / "web")', spec)
        self.assertIn('"PySide6.QtWebEngineCore"', spec)
        self.assertIn('"PySide6.QtWebEngineWidgets"', spec)
        self.assertNotIn('excludes=["tkinter", "PySide6.QtWebEngineCore"', spec)

    def test_windows_service_bundles_and_serves_exact_reference_ui(self) -> None:
        service_spec = (ROOT / "build" / "windows" / "service.spec").read_text(encoding="utf-8")
        service = (ROOT / "src" / "sazmanhr" / "windows_service.py").read_text(encoding="utf-8")
        smoke = (ROOT / "build" / "windows" / "smoke-install.ps1").read_text(encoding="utf-8")
        self.assertIn('str(root / "web")', service_spec)
        self.assertIn("_service_web_root()", service)
        self.assertIn("web_root=_service_web_root()", service)
        self.assertIn("Exact SazmanHR v4.9 web UI is missing", service)
        self.assertIn("Assert-ExactV49UiRoot", smoke)
        self.assertIn(REFERENCE_HASHES["index.html"], smoke)
        self.assertIn("served by Windows Service", smoke)


    def test_frozen_builder_runs_ui_smoke_before_installer(self) -> None:
        builder = (ROOT / "build" / "windows" / "build_windows.py").read_text(encoding="utf-8")
        ui_smoke = builder.index('"--ui-smoke-test"')
        inno = builder.index('iscc = install_inno(log)')
        self.assertLess(ui_smoke, inno)


if __name__ == "__main__":
    unittest.main()
