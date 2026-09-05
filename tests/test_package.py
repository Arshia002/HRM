import hashlib
import ast
import importlib.util
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
GENERATED_PARTS = {
    "build-output", "__pycache__", ".git", ".venv", "venv",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".nox",
}


class PackageTests(unittest.TestCase):
    def test_manifest_matches_database(self):
        database = PROJECT / "data" / "seed" / "sazmanhr-seed.sqlite"
        manifest = json.loads((PROJECT / "data" / "seed" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(hashlib.sha256(database.read_bytes()).hexdigest(), manifest["database_sha256"])
        conn = sqlite3.connect(database)
        try:
            self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM personnel").fetchone()[0], 36)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM chart_pages").fetchone()[0], 53)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()[0], "5")
            self.assertEqual(conn.execute("SELECT value FROM metadata WHERE key='product_id'").fetchone()[0],
                             "sazmanhr-enterprise")
            self.assertEqual(conn.execute("SELECT value FROM metadata WHERE key='schema_generation'").fetchone()[0],
                             "16")
        finally:
            conn.close()

    def test_no_executable_payload_is_bundled(self):
        forbidden = {".exe", ".dll", ".msi", ".sys"}
        found = [
            str(path.relative_to(PROJECT))
            for path in PROJECT.rglob("*")
            if path.suffix.lower() in forbidden
            and not any(part in GENERATED_PARTS for part in path.relative_to(PROJECT).parts)
        ]
        self.assertEqual(found, [])

    def test_isolated_local_gate_environment_is_never_packaged(self):
        gitignore = (PROJECT / ".gitignore").read_text(encoding="utf-8")
        builder = (PROJECT / "tools" / "build_release.py").read_text(encoding="utf-8")
        apply = (PROJECT / "APPLY-V080RC1.cmd").read_text(encoding="utf-8")
        manifest = json.loads((PROJECT / "PACKAGE-MANIFEST.json").read_text(encoding="utf-8"))
        self.assertIn(".venv/", gitignore)
        self.assertIn('".venv"', builder)
        self.assertIn("python -m venv .venv", apply)
        self.assertIn("--only-binary=:all: -r ci\\requirements-source-gates.txt", apply)
        self.assertIn("ci\\validate_v080rc1_candidate.py", apply)
        self.assertFalse(any(".venv" in Path(item["path"]).parts for item in manifest["files"]))

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
                         and not any(part in GENERATED_PARTS for part in path.relative_to(PROJECT).parts))
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

    def test_bootstrap_secret_is_random_and_not_logged(self):
        server = (PROJECT / "src" / "sazmanhr" / "server.py").read_text(encoding="utf-8")
        security = (PROJECT / "src" / "sazmanhr" / "security.py").read_text(encoding="utf-8")
        installer = (PROJECT / "build" / "windows" / "HRM.iss").read_text(encoding="utf-8")
        smoke = (PROJECT / "build" / "windows" / "smoke-install.ps1").read_text(encoding="utf-8")
        retired_secret = "1381" + "1381"
        self.assertIn("generate_temporary_password()", server)
        self.assertNotIn("One-time password:", server)
        self.assertNotIn(retired_secret, server + security + installer + smoke)
        self.assertIn("Password:\\s*(.+)", smoke)


    def test_pyinstaller_spec_names_match_windows_builder_contract(self):
        import ast as _ast

        expected = {
            "client.spec": "HRM",
            "server.spec": "HRMServer",
            "service.spec": "HRMService",
            "migration.spec": "HRMMigration",
        }
        for spec_name, expected_name in expected.items():
            path = PROJECT / "build" / "windows" / spec_name
            tree = _ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            names = []
            for node in _ast.walk(tree):
                if isinstance(node, _ast.Call) and isinstance(node.func, _ast.Name) and node.func.id == "EXE":
                    for keyword in node.keywords:
                        if keyword.arg == "name" and isinstance(keyword.value, _ast.Constant):
                            names.append(keyword.value.value)
            self.assertEqual(names, [expected_name], f"{spec_name} must emit {expected_name}.exe")

    def test_inno_sources_are_existing_ascii_safe_files(self):
        import re as _re

        script = (PROJECT / "build" / "windows" / "HRM.iss").read_text(encoding="utf-8")
        sources = _re.findall(r'^Source:\s*"\{#ProjectRoot\}\\([^\"]+)"', script, _re.MULTILINE)
        self.assertTrue(sources)
        for raw in sources:
            raw.encode("ascii")
            source_path = PROJECT.joinpath(*raw.split("\\"))
            self.assertTrue(source_path.is_file(), f"Missing Inno source: {raw}")
        self.assertIn(r'docs\deployment-guide-fa.md', sources)
        self.assertIn(r'docs\windows-test-checklist-fa.md', sources)


    def test_ci_package_manifest_paths_are_ascii_safe_for_windows_zip_roundtrip(self):
        manifest = json.loads((PROJECT / "PACKAGE-MANIFEST.json").read_text(encoding="utf-8"))
        paths = [item["path"] for item in manifest["files"]]
        self.assertTrue(paths)
        self.assertEqual(len(paths), len(set(paths)))
        for relative in paths:
            relative.encode("ascii")
            pure = Path(relative)
            self.assertNotIn("..", pure.parts)
            self.assertTrue((PROJECT / pure).is_file(), f"Missing overlay file: {relative}")

    def test_unrelated_unicode_repository_docs_do_not_expand_ci_package_contract(self):
        # Regression for alpha.3 pre-push: historical Persian-named docs may
        # exist in the repository, but they are not part of the CI overlay or
        # Inno installer payload. The manifest is the archive boundary.
        manifest = json.loads((PROJECT / "PACKAGE-MANIFEST.json").read_text(encoding="utf-8"))
        packaged = {item["path"] for item in manifest["files"]}
        self.assertNotIn("docs/امنیت.md", packaged)
        self.assertNotIn("docs/راهنمای-استقرار.md", packaged)

    def test_fail_fast_packaging_contract_validator(self):
        result = subprocess.run(
            [sys.executable, str(PROJECT / "ci" / "validate_package_contract.py")],
            cwd=PROJECT, text=True, capture_output=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("ALL PACKAGE CONTRACT CHECKS PASSED", result.stdout)

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
        self.assertIn("hrmcentral", lowered)
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
        acl = lowered.index("nt service\\hrmcentralservice:(oi)(ci)m")
        hardening = lowered.index("/inheritance:d /t")
        final_health = lowered.index("آزمون نهایی tls")
        self.assertLess(service, service_sid)
        self.assertLess(service_sid, acl)
        self.assertLess(acl, hardening)
        self.assertLess(hardening, final_health)
        self.assertIn('config hrmcentralservice obj= "nt authority\\localservice" password= ""', lowered)
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
        self.assertIn("version -ne '0.8.0-rc.1'", lowered)
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
        self.assertIn("actions/checkout@v7", workflow)
        self.assertIn("actions/setup-python@v7", workflow)
        self.assertIn("actions/upload-artifact@v7", workflow)
        self.assertIn("permissions:\n  contents: read", workflow)

    def test_ci_manifest_never_contains_local_cache_or_generated_worktree_paths(self):
        manifest = json.loads((PROJECT / "PACKAGE-MANIFEST.json").read_text(encoding="utf-8"))
        forbidden_parts = {".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".nox", ".venv", "venv", "__pycache__", "build-output", ".git"}
        for item in manifest["files"]:
            parts = Path(item["path"]).parts
            self.assertFalse(forbidden_parts.intersection(parts), item["path"])

    def test_corrected_beta_package_has_distinct_ci_revision(self):
        self.assertEqual(
            (PROJECT / "CI-PACKAGE-VERSION").read_text(encoding="utf-8").strip(),
            "0.8.0-rc.1-ci.1",
        )
        builder = (PROJECT / "tools" / "build_release.py").read_text(encoding="utf-8")
        self.assertIn("PACKAGE_REVISION", builder)
        self.assertIn('"package_revision": PACKAGE_REVISION', builder)

    def test_overlay_integrity_gate_precedes_manifest_regeneration(self):
        apply = (PROJECT / "APPLY-V080RC1.cmd").read_text(encoding="utf-8")
        verify = apply.index("ci\\validate_overlay_integrity.py")
        regenerate = apply.index("tools\\build_release.py")
        self.assertLess(verify, regenerate)

    def test_overlay_integrity_rejects_a_mixed_revision_payload(self):
        from ci.validate_overlay_integrity import OverlayIntegrityError, verify_overlay

        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            payload = root / "payload.txt"
            payload.write_text("ci.5 payload\n", encoding="utf-8", newline="\n")
            raw = payload.read_bytes()
            (root / "CI-PACKAGE-VERSION").write_text(
                "0.8.0-rc.1-ci.1\n", encoding="utf-8", newline="\n"
            )
            manifest = {
                "package_revision": "0.8.0-rc.1-ci.1",
                "files": [{
                    "path": "payload.txt", "bytes": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                }],
            }
            (root / "PACKAGE-MANIFEST.json").write_text(
                json.dumps(manifest), encoding="utf-8", newline="\n"
            )
            self.assertEqual(verify_overlay(root), 1)
            payload.write_text("stale ci.4 payload\n", encoding="utf-8", newline="\n")
            with self.assertRaisesRegex(OverlayIntegrityError, "byte count mismatch"):
                verify_overlay(root)

    def test_release_builder_excludes_mutable_local_test_logs(self):
        builder = (PROJECT / "tools" / "build_release.py").read_text(encoding="utf-8")
        self.assertIn('".log"', builder)
        manifest = json.loads((PROJECT / "PACKAGE-MANIFEST.json").read_text(encoding="utf-8"))
        self.assertFalse(any(item["path"].endswith(".log") for item in manifest["files"]))

    def test_release_builder_explicitly_excludes_pytest_cache(self):
        builder = (PROJECT / "tools" / "build_release.py").read_text(encoding="utf-8")
        self.assertIn('".pytest_cache"', builder)
        self.assertIn("is_stable_overlay_file", builder)
        self.assertNotIn('for path in sorted(ROOT.rglob("*")):\n        relative = path.relative_to(ROOT)', builder)

    def test_manifest_gate_verifies_content_hashes(self):
        validator = (PROJECT / "ci" / "validate_package_contract.py").read_text(encoding="utf-8")
        self.assertIn("Package manifest SHA-256 mismatch", validator)
        self.assertIn("sha256_file", validator)

    def test_clean_checkout_gate_requires_manifest_files_in_git(self):
        validator = (PROJECT / "ci" / "validate_package_contract.py").read_text(encoding="utf-8")
        self.assertIn("--require-git-tracked", validator)
        self.assertIn('["git", "ls-files", "-z"]', validator)
        workflow = (PROJECT / ".github" / "workflows" / "windows-build.yml").read_text(encoding="utf-8")
        self.assertIn("validate_package_contract.py --require-git-tracked", workflow)

    def test_guarded_push_runs_v060_gates_before_commit(self):
        push = (PROJECT / "PUSH-TO-GITHUB.cmd").read_text(encoding="utf-8")
        gate = push.index('call "%~dp0APPLY-V080RC1.cmd"')
        stage = push.index("ci\\stage_v080rc1_overlay.py")
        commit = push.index("git commit -m")
        remote = push.index("git push -u origin %HRM_PILOT_BRANCH%")
        self.assertLess(gate, stage)
        self.assertLess(stage, commit)
        self.assertLess(commit, remote)
        self.assertIn("local %HRM_VERSION% gates failed. Nothing will be committed or pushed", push)
        self.assertIn(".venv\\Scripts\\python.exe", push)
        self.assertNotIn("git add -A", push)
        self.assertNotIn("git switch", push.lower())
        self.assertIn("git branch --show-current", push)

    def test_rc_installer_forces_manifest_driven_complete_overlay_before_push(self):
        installer = (PROJECT / "INSTALL-OVERLAY-V080RC1.cmd").read_text(encoding="utf-8")
        self.assertIn("release_identity.py\" --print branch", installer)
        self.assertIn("%HRM_PILOT_BRANCH%", installer)
        self.assertIn("install_verified_overlay.py", installer)
        self.assertNotIn("robocopy", installer.lower())
        first_verify = installer.index("validate_overlay_integrity.py")
        copy = installer.index("install_verified_overlay.py")
        second_verify = installer.index("validate_overlay_integrity.py", first_verify + 1)
        self.assertLess(first_verify, copy)
        self.assertLess(copy, second_verify)

    def test_manifest_installer_overwrites_payload_independent_of_metadata(self):
        source = (PROJECT / "ci" / "install_verified_overlay.py").read_text(encoding="utf-8")
        self.assertIn("shutil.copyfile", source)
        self.assertIn("sha256_file", source)
        self.assertIn("PACKAGE-MANIFEST.json", source)
        self.assertIn("Installed payload verification failed", source)

    def test_guarded_stage_is_manifest_limited(self):
        stage = (PROJECT / "ci" / "stage_v080rc1_overlay.py").read_text(encoding="utf-8")
        self.assertIn('"PACKAGE-MANIFEST.json", "SHA256SUMS.txt"', stage)
        self.assertIn('staged - set(paths)', stage)
        self.assertIn('"git", "add", "--"', stage)

    def test_protected_real_data_boundary_excludes_plaintext_key_and_artifacts(self):
        manifest = json.loads((PROJECT / "PACKAGE-MANIFEST.json").read_text(encoding="utf-8"))
        paths = {item["path"] for item in manifest["files"]}
        self.assertFalse(any(path.lower().endswith((".key", ".xls", ".xlsx", ".csv")) for path in paths))
        self.assertFalse(any(path.startswith("private-data/") for path in paths))
        workflow = (PROJECT / ".github" / "workflows" / "windows-build.yml").read_text(encoding="utf-8")
        self.assertIn("environment: real-data-validation", workflow)
        self.assertIn("secrets.HRM_REAL_DATA_KEY", workflow)
        self.assertIn("real-data-validation-summary.json", workflow)
        self.assertNotRegex(workflow, r"(?mi)^\s+ci[/\\]real-data[/\\].*$")

    def test_proven_alpha4_upgrade_contract_is_preserved(self):
        script = (PROJECT / "build" / "windows" / "HRM.iss").read_text(encoding="utf-8").lower()
        smoke = (PROJECT / "build" / "windows" / "smoke-install.ps1").read_text(encoding="utf-8").lower()
        self.assertIn("service-stop-before-copy", script)
        self.assertIn("--stop-windows-service hrmcentralservice", script)
        self.assertIn('config hrmcentralservice obj= "nt authority\\localservice" password= ""', script)
        self.assertIn("sidtype hrmcentralservice unrestricted", script)
        self.assertIn("service-stop-before-copy", smoke)
        self.assertIn("firstfileentryindex", smoke)
        self.assertIn("nt authority\\localservice", smoke)
        self.assertNotIn("hrmcentral obj= localsystem", script)

    def test_frozen_qt_client_smoke_test_is_restored(self):
        client = (PROJECT / "src" / "sazmanhr" / "client.py").read_text(encoding="utf-8")
        builder = (PROJECT / "build" / "windows" / "build_windows.py").read_text(encoding="utf-8")
        self.assertIn('--smoke-test', client)
        self.assertIn('[DIST_DIR / "HRM.exe", "--smoke-test"]', builder)

    def test_public_installer_does_not_persist_synthetic_seed(self):
        script = (PROJECT / "build" / "windows" / "HRM.iss").read_text(encoding="utf-8")
        self.assertIn('DestName: "hrm-seed.sqlite"', script)
        self.assertIn('Flags: dontcopy noencryption', script)
        self.assertNotIn('DestDir: "{app}\\Server\\data\\seed"', script)


    def test_native_windows_personnel_movements_are_exposed_and_direct_org_edit_is_locked(self):
        client = (PROJECT / "src" / "sazmanhr" / "client.py").read_text(encoding="utf-8")
        server = (PROJECT / "src" / "sazmanhr" / "server.py").read_text(encoding="utf-8")
        permissions = (PROJECT / "src" / "sazmanhr" / "database.py").read_text(encoding="utf-8")
        self.assertIn("ثبت جابه‌جایی", client)
        self.assertIn("سوابق جابه‌جایی سازمانی", client)
        self.assertIn("MOVEMENT_FIELDS", client)
        self.assertIn('"code": "movement_required"', server)
        self.assertIn('self.repo.require(user, "reverse_movements")', server)
        self.assertIn('"reverse_movements": "ابطال آخرین جابه‌جایی پرسنلی"', permissions)

    def test_linux_web_test_is_shared_core_dockerized_and_explicitly_nonproduction(self):
        dockerfile = (PROJECT / "deploy" / "linux-web-test" / "Dockerfile").read_text(encoding="utf-8")
        compose = (PROJECT / "deploy" / "linux-web-test" / "docker-compose.yml").read_text(encoding="utf-8")
        web = (PROJECT / "web" / "index.html").read_text(encoding="utf-8")
        builder = (PROJECT / "tools" / "build_linux_web_test.py").read_text(encoding="utf-8")
        workflow = (PROJECT / ".github" / "workflows" / "windows-build.yml").read_text(encoding="utf-8")
        self.assertIn("NOT FOR PRODUCTION", web)
        self.assertIn("PYTHONPATH=/app/src", dockerfile)
        self.assertIn("127.0.0.1:${HRM_WEB_PORT:-8080}:8080", compose)
        self.assertIn("linux-web-test-not-for-production", builder)
        self.assertIn("docker build -f deploy/linux-web-test/Dockerfile", workflow)
        self.assertIn("HRM-0.8.0-rc.1-Linux-Web-Test", workflow)


if __name__ == "__main__":
    unittest.main()
