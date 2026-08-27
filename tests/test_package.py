import hashlib
import ast
import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from sazmanhr.demo_data import DEMO_CHART_PAGE_COUNT, DEMO_PERSONNEL_COUNT, create_demo_seed


PROJECT = Path(__file__).resolve().parents[1]
GENERATED_PARTS = {"build-output", "__pycache__", ".git"}


def is_generated(path: Path) -> bool:
    parts = path.relative_to(PROJECT).parts
    return any(part in GENERATED_PARTS or part.startswith("tmp") for part in parts)


class PackageTests(unittest.TestCase):
    def test_manifest_matches_database(self):
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / "hrm-seed.sqlite"
            generated = create_demo_seed(database)
            manifest = json.loads(database.with_name("manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(generated, manifest)
            self.assertEqual(hashlib.sha256(database.read_bytes()).hexdigest(), manifest["database_sha256"])
            conn = sqlite3.connect(database)
            try:
                self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM personnel").fetchone()[0], DEMO_PERSONNEL_COUNT)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM chart_pages").fetchone()[0], DEMO_CHART_PAGE_COUNT)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0], 0)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0], 0)
                self.assertEqual(conn.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()[0], "5")
                self.assertEqual(conn.execute("SELECT value FROM metadata WHERE key='product_id'").fetchone()[0],
                                 "hrm-kepdco")
                self.assertEqual(conn.execute("SELECT value FROM metadata WHERE key='schema_generation'").fetchone()[0],
                                 "1")
            finally:
                conn.close()

    def test_no_sensitive_source_data_is_tracked_in_package(self):
        forbidden = {".xls", ".xlsx", ".xlsm", ".ppt", ".pptx", ".zip", ".7z", ".rar", ".sqlite", ".db"}
        found = [
            str(path.relative_to(PROJECT))
            for path in PROJECT.rglob("*")
            if path.is_file()
            and path.suffix.lower() in forbidden
            and not is_generated(path)
        ]
        self.assertEqual(found, [])

    def test_no_executable_payload_is_bundled(self):
        forbidden = {".exe", ".dll", ".msi", ".sys"}
        found = [
            str(path.relative_to(PROJECT))
            for path in PROJECT.rglob("*")
            if path.suffix.lower() in forbidden
            and not is_generated(path)
        ]
        self.assertEqual(found, [])

    def test_native_client_has_no_browser_engine(self):
        source = "\n".join(path.read_text(encoding="utf-8") for path in (PROJECT / "src").rglob("*.py")).lower()
        for forbidden in ("webview", "webbrowser", "chromium", "electron"):
            self.assertNotIn(forbidden, source)
        client = (PROJECT / "src" / "sazmanhr" / "client.py").read_text(encoding="utf-8")
        self.assertIn("PySide6", client)
        self.assertNotIn("tkinter", client.lower())

    def test_no_previous_broken_release_markers(self):
        suffixes = {".py", ".md", ".txt", ".toml", ".iss", ".ps1", ".cmd", ".yml"}
        text = "\n".join(path.read_text(encoding="utf-8", errors="ignore")
                         for path in PROJECT.rglob("*")
                         if path.is_file()
                         and path.suffix.lower() in suffixes
                         and path.name != "test_package.py"
                         and not is_generated(path))
        lowered = text.lower()
        for marker in ("r11", "r12", "r13", "r14", "5.1.1-network", "5.1.2-network", "windows_postinstall"):
            self.assertNotIn(marker, lowered)

    def test_one_click_builder_does_not_invoke_powershell(self):
        launcher = (PROJECT / "BUILD-SETUP.cmd").read_text(encoding="utf-8").lower()
        self.assertIn("build_windows.py", launcher)
        self.assertNotIn("powershell.exe", launcher)
        self.assertNotIn("bootstrap-build.ps1", launcher)

    def test_native_windows_builder_is_valid_python(self):
        builder = PROJECT / "build" / "windows" / "build_windows.py"
        self.assertTrue(builder.is_file())
        ast.parse(builder.read_text(encoding="utf-8"), filename=str(builder))

    def test_windows_builder_console_handles_persian_paths(self):
        builder = PROJECT / "build" / "windows" / "build_windows.py"
        spec = importlib.util.spec_from_file_location("sazmanhr_build_windows", builder)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        escaped = module.console_safe_text("docs/راهنمای-استقرار.md", "cp1252")
        escaped.encode("cp1252", errors="strict")
        self.assertIn("\\u", escaped)
        self.assertEqual(module.console_safe_text("راهنما", "utf-8"), "راهنما")

    def test_installer_is_offline_isolated_and_fail_fast(self):
        script = (PROJECT / "build" / "windows" / "HRM.iss").read_text(encoding="utf-8")
        lowered = script.lower()
        self.assertIn("hrm-kermanshah", lowered)
        self.assertIn("hrmcentralservice", lowered)
        self.assertIn("--health-check", lowered)
        self.assertIn("hrmserverpreflight.exe", lowered)
        self.assertIn("preparetoinstall", lowered)
        self.assertIn("getcustomsetupexitcode", lowered)
        self.assertIn("runrequired", lowered)
        self.assertIn("raiseexception", lowered)
        self.assertNotIn("{commonappdata}\\sazmanhr\\", lowered)
        self.assertNotIn("sazmanhrcentral", lowered)
        for forbidden in ("python.exe", "pip install", "winget", "powershell", "download"):
            self.assertNotIn(forbidden, lowered)

    def test_private_seed_is_injected_at_setup_build_time(self):
        for name in ("server.spec", "service.spec"):
            spec = (PROJECT / "build" / "windows" / name).read_text(encoding="utf-8")
            self.assertIn("datas=[]", spec)
            self.assertNotIn("hrm-seed.sqlite", spec)
        installer = (PROJECT / "build" / "windows" / "HRM.iss").read_text(encoding="utf-8")
        builder = (PROJECT / "build" / "windows" / "build_windows.py").read_text(encoding="utf-8")
        self.assertIn("#ifndef SeedPath", installer)
        self.assertIn('Source: "{#SeedPath}"', installer)
        self.assertIn('f"/DSeedPath={seed_path}"', builder)
        self.assertIn('parser.add_argument(\n        "--seed"', builder)

    def test_private_seed_is_not_left_in_program_files(self):
        installer = (PROJECT / "build" / "windows" / "HRM.iss").read_text(encoding="utf-8")
        lowered = installer.lower()
        self.assertNotIn('destdir: "{app}\\server\\data\\seed"', lowered)
        self.assertIn("seedpath := expandconstant('{tmp}\\hrm-seed.sqlite')", lowered)
        self.assertIn('flags: dontcopy', lowered)

    def test_build_is_versioned_and_emits_provenance(self):
        installer = (PROJECT / "build" / "windows" / "HRM.iss").read_text(encoding="utf-8")
        builder = (PROJECT / "build" / "windows" / "build_windows.py").read_text(encoding="utf-8")
        client = (PROJECT / "src" / "sazmanhr" / "client.py").read_text(encoding="utf-8")
        self.assertIn("#ifndef AppVersion", installer)
        self.assertIn("AppVersion={#AppVersion}", installer)
        self.assertIn('f"/DAppVersion={version}"', builder)
        self.assertIn("build-manifest.json", builder)
        self.assertIn("dependencies.txt", builder)
        self.assertIn('DIST_DIR / "HRM.exe", "--smoke-test"', builder)
        self.assertIn('parser.add_argument("--smoke-test"', client)

    def test_build_dependencies_are_exactly_pinned(self):
        requirements = (PROJECT / "build" / "windows" / "requirements-build.txt").read_text(
            encoding="utf-8"
        ).splitlines()
        pins = [line for line in requirements if line.strip() and not line.lstrip().startswith("#")]
        self.assertGreaterEqual(len(pins), 4)
        self.assertTrue(all(line.count("==") == 1 for line in pins))

    def test_silent_installer_has_no_unsuppressible_message_box(self):
        script = (PROJECT / "build" / "windows" / "HRM.iss").read_text(encoding="utf-8")
        self.assertIn("SuppressibleMsgBox(", script)
        self.assertNotRegex(script, r"(?m)^\s*MsgBox\(")

    def test_windows_install_smoke_test_has_process_timeouts_and_setup_log(self):
        script = (PROJECT / "build" / "windows" / "smoke-install.ps1").read_text(encoding="utf-8")
        self.assertIn("WaitForExit($TimeoutSeconds * 1000)", script)
        self.assertIn("taskkill.exe", script)
        self.assertIn('/LOG=`"$SetupLog`"', script)
        self.assertNotIn("Start-Process $Installer", script)

    def test_installer_registers_service_before_acl_and_verifies_hardening(self):
        script = (PROJECT / "build" / "windows" / "HRM.iss").read_text(encoding="utf-8")
        lowered = script.lower()
        service = lowered.index("--startup auto install")
        service_sid = lowered.index("sidtype hrmcentralservice unrestricted")
        service_sid_check = lowered.index("qsidtype hrmcentralservice")
        service_account = lowered.index('config hrmcentralservice obj= "nt authority\\localservice"')
        acl = lowered.index("nt service\\hrmcentralservice:(oi)(ci)m")
        hardening = lowered.index("/inheritance:r /t")
        final_health = lowered.index("آزمون نهایی tls")
        self.assertLess(service, service_sid)
        self.assertLess(service_sid, service_sid_check)
        self.assertLess(service_sid_check, service_account)
        self.assertLess(service_account, acl)
        self.assertLess(acl, hardening)
        self.assertLess(hardening, final_health)
        self.assertNotIn('obj= "nt service\\hrmcentralservice"', lowered)
        self.assertIn("hrm_stage|", lowered)
        self.assertIn("logprotecteddiagnostics", lowered)
        self.assertNotIn("/t /c", lowered)

    def test_windows_smoke_test_verifies_service_identity_acl_and_diagnostics(self):
        script = (PROJECT / "build" / "windows" / "smoke-install.ps1").read_text(encoding="utf-8")
        lowered = script.lower()
        self.assertIn("get-ciminstance win32_service", lowered)
        self.assertIn("startname -ne 'nt authority\\localservice'", lowered)
        self.assertIn("nt service", lowered)
        self.assertIn("filesystemrights]::modify", lowered)
        self.assertIn("database -ne 'ready'", lowered)
        self.assertIn("version -ne $expectedversion", lowered)
        self.assertIn("build-manifest.json", lowered)
        self.assertNotIn("frozen database verification", lowered)
        self.assertNotIn("--verify-database", lowered)
        self.assertLess(lowered.index("stop-transcript"), lowered.index("copy-item -force $serverlog"))
        self.assertIn("install-failure-summary.txt", lowered)
        self.assertIn("diagnostic-copy-errors.txt", lowered)
        self.assertIn("service-config.txt", lowered)
        self.assertIn("data-acl.txt", lowered)
        workflow = (PROJECT / ".github" / "workflows" / "windows-build.yml").read_text(encoding="utf-8").lower()
        self.assertIn("snapshot installer diagnostics", workflow)
        self.assertIn("build-output/installer/*.log", workflow)
        self.assertIn("build-output/installer/*.json", workflow)
        self.assertRegex(workflow, r"actions/checkout@[0-9a-f]{40}\s+# v7\.0\.1")
        self.assertRegex(workflow, r"actions/setup-python@[0-9a-f]{40}\s+# v7\.0\.0")
        self.assertRegex(workflow, r"actions/upload-artifact@[0-9a-f]{40}\s+# v7\.0\.1")
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn("build-manifest.json", workflow)
        self.assertIn("dependencies.txt", workflow)
        self.assertIn("permissions:\n  contents: read", workflow)


if __name__ == "__main__":
    unittest.main()
