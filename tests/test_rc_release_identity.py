import json, unittest
from pathlib import Path
from ci.release_identity import load_identity

ROOT=Path(__file__).resolve().parents[1]
class RcReleaseIdentityTests(unittest.TestCase):
    def test_rc_identity_is_single_contract(self):
        x=load_identity()
        self.assertEqual(x.version,'0.7.0-rc.1')
        self.assertEqual(x.package_revision,'0.7.0-rc.1-ci.4')
        self.assertEqual(x.branch,'feat/organizational-pilot-v070rc1')
        self.assertEqual(x.baseline_tag,'v0.6.0-beta.1')
        self.assertEqual(x.baseline_commit,'a8b93c981603c58d0edaf3d999e088c7a674aa1b')
    def test_workflow_and_push_match_identity(self):
        x=load_identity(); w=(ROOT/'.github/workflows/windows-build.yml').read_text(encoding='utf-8'); p=(ROOT/'PUSH-TO-GITHUB.cmd').read_text(encoding='utf-8')
        self.assertIn(x.branch,w); self.assertIn(x.tested_artifact,w)
        self.assertIn('release_identity.py --print branch',p)
        self.assertIn('release_identity.py --print baseline_commit',p)
