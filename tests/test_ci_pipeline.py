import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]


class CiPipelineTests(unittest.TestCase):
    def test_windows_ci_contract(self):
        workflow = (PROJECT / ".github" / "workflows" / "windows-build.yml").read_text(encoding="utf-8")
        smoke = (PROJECT / "build" / "windows" / "smoke-install.ps1").read_text(encoding="utf-8")
        manifest = (PROJECT / "ci" / "write-ci-manifest.ps1").read_text(encoding="utf-8")

        self.assertIn("feat/native-v49-shell", workflow)
        self.assertIn("HRM-0.2.0-alpha.2-Tested-Setup", workflow)
        self.assertIn("HRM-0.2.0-alpha.2-Failure-Logs", workflow)
        self.assertIn("write-ci-manifest.ps1", workflow)
        self.assertIn("Validate packaging contract", workflow)
        self.assertIn("validate_package_contract.py", workflow)
        self.assertIn("contract-validation.log", workflow)
        self.assertIn("setup-upgrade.log", workflow)

        self.assertIn("13811381", smoke)
        self.assertIn("Dashboard blocked before password change", smoke)
        self.assertIn("Bootstrap password invalidated after change", smoke)
        self.assertIn("Silent in-place upgrade installation", smoke)
        self.assertIn("Bootstrap password remains invalid after upgrade", smoke)
        self.assertIn("Operational database was removed by uninstall", smoke)

        self.assertIn("bootstrap_login = $true", manifest)
        self.assertIn("in_place_upgrade = $true", manifest)
        self.assertIn("uninstall_preserves_data = $true", manifest)


if __name__ == "__main__":
    unittest.main()
