import unittest
import importlib.metadata
from pathlib import Path

from ci.validate_v040a3_candidate import dependency_errors, pinned_requirements


PROJECT = Path(__file__).resolve().parents[1]


class CiPipelineTests(unittest.TestCase):
    def test_windows_ci_contract(self):
        workflow = (PROJECT / ".github" / "workflows" / "windows-build.yml").read_text(encoding="utf-8")
        smoke = (PROJECT / "build" / "windows" / "smoke-install.ps1").read_text(encoding="utf-8")
        manifest = (PROJECT / "ci" / "write-ci-manifest.ps1").read_text(encoding="utf-8")

        self.assertIn("feat/native-v49-shell", workflow)
        self.assertIn("HRM-0.4.0-alpha.3-Tested-Setup", workflow)
        self.assertIn("HRM-0.4.0-alpha.3-Failure-Logs", workflow)
        self.assertIn("write-ci-manifest.ps1", workflow)
        self.assertIn("Validate packaging contract", workflow)
        self.assertIn("validate_package_contract.py", workflow)
        self.assertIn("--require-git-tracked", workflow)
        self.assertIn("contract-validation.log", workflow)
        self.assertIn("setup-upgrade.log", workflow)

        self.assertIn("Random bootstrap password was not found", smoke)
        self.assertIn("FIRST_LOGIN.txt", smoke)
        self.assertIn("Dashboard blocked before password change", smoke)
        self.assertIn("Bootstrap password invalidated after change", smoke)
        self.assertIn("Silent in-place upgrade installation", smoke)
        self.assertIn("Bootstrap password remains invalid after upgrade", smoke)
        self.assertIn("Operational database was removed by uninstall", smoke)

        self.assertIn("bootstrap_login = $true", manifest)
        self.assertIn("in_place_upgrade = $true", manifest)
        self.assertIn("uninstall_preserves_data = $true", manifest)
        self.assertIn("service_identity = 'NT AUTHORITY\\LocalService'", manifest)
        self.assertIn("Tee-Object -FilePath .\\migration-validation.log", workflow)
        self.assertGreaterEqual(workflow.count("migration-validation.log"), 3)

    def test_source_dependencies_precede_migration_and_inno(self):
        workflow = (PROJECT / ".github" / "workflows" / "windows-build.yml").read_text(encoding="utf-8")
        contract = workflow.index("Validate packaging contract")
        dependencies = workflow.index("Install source gate dependencies")
        migration = workflow.index("Validate v0.4.0 alpha.3 clean runner candidate")
        inno = workflow.index("Install Inno Setup")
        build = workflow.index("Build and unit test")
        self.assertLess(contract, dependencies)
        self.assertLess(dependencies, migration)
        self.assertLess(migration, inno)
        self.assertLess(inno, build)
        self.assertIn("--only-binary=:all: -r .\\ci\\requirements-source-gates.txt", workflow)
        self.assertIn("cache-dependency-path", workflow)
        self.assertGreaterEqual(workflow.count("source-gate-dependencies.log"), 3)

    def test_source_dependency_pins_match_build_and_report_missing_modules(self):
        source = pinned_requirements(PROJECT / "ci" / "requirements-source-gates.txt")
        build = pinned_requirements(PROJECT / "build" / "windows" / "requirements-build.txt")
        self.assertEqual(
            source,
            {"cryptography": "50.0.1", "openpyxl": "3.1.5", "xlrd": "2.0.1"},
        )
        self.assertTrue(all(build.get(name) == version for name, version in source.items()))

        def missing(name: str) -> str:
            if name == "openpyxl":
                raise importlib.metadata.PackageNotFoundError(name)
            return source[name]

        self.assertEqual(dependency_errors(source, missing), ["openpyxl missing (expected 3.1.5)"])


if __name__ == "__main__":
    unittest.main()
