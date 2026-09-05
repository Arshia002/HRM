import json, unittest
from pathlib import Path
from ci.release_identity import load_identity

ROOT=Path(__file__).resolve().parents[1]
class RcReleaseIdentityTests(unittest.TestCase):
    def test_rc_identity_is_single_contract(self):
        x=load_identity()
        self.assertEqual(x.version,'0.8.0-rc.1')
        self.assertEqual(x.package_revision,'0.8.0-rc.1-ci.1')
        self.assertEqual(x.branch,'feat/production-history-web-v080rc1')
        self.assertEqual(x.baseline_tag,'tested-v0.7.0-rc.1-source')
        self.assertEqual(x.baseline_commit,'2a1a7f7b71b3a01c9f459f17d13d9dc348f45fb2')
    def test_workflow_and_push_match_identity(self):
        x=load_identity(); w=(ROOT/'.github/workflows/windows-build.yml').read_text(encoding='utf-8'); p=(ROOT/'PUSH-TO-GITHUB.cmd').read_text(encoding='utf-8')
        self.assertIn(x.branch,w); self.assertIn(x.tested_artifact,w)
        self.assertIn('release_identity.py --print branch',p)
        self.assertIn('release_identity.py --print baseline_commit',p)
