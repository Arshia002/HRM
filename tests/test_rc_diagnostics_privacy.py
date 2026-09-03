import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class RcDiagnosticsPrivacyTests(unittest.TestCase):
    def test_installed_diagnostics_are_structurally_redacted(self):
        ps=(ROOT/'tools/collect-diagnostics.ps1').read_text(encoding='utf-8')
        self.assertIn("message=$x.message",ps); self.assertIn("request_id=$x.request_id",ps)
        for forbidden in ('client=$x.client','detail=$x.detail','exception=$x.exception','FIRST_LOGIN','hrm.sqlite'):
            self.assertNotIn(forbidden,ps)
        cmd=(ROOT/'tools/collect-diagnostics.cmd').read_text(encoding='utf-8'); self.assertIn('collect-diagnostics.ps1',cmd)
        iss=(ROOT/'build/windows/HRM.iss').read_text(encoding='utf-8'); self.assertIn('tools\\collect-diagnostics.ps1',iss)
