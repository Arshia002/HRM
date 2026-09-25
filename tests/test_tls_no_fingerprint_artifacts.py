# Regression contract: TLS stays enabled while certificate fingerprint pinning/artifacts are removed.
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sazmanhr.tls import ensure_self_signed_certificate


ROOT = Path(__file__).resolve().parents[1]


class TlsNoFingerprintArtifactsTests(unittest.TestCase):
    def test_product_sources_do_not_contain_active_fingerprint_contract(self):
        paths = [
            ROOT / "src" / "sazmanhr" / "server.py",
            ROOT / "src" / "sazmanhr" / "tls.py",
            ROOT / "src" / "sazmanhr" / "windows_service.py",
        ]
        combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)
        forbidden = (
            "tls_fingerprint",
            "certificate_fingerprint",
            "pem_fingerprint",
            "remote_fingerprint",
        )
        for marker in forbidden:
            self.assertNotIn(marker, combined, marker)

        active_notice_sources = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (
                ROOT / "src" / "sazmanhr" / "server.py",
                ROOT / "src" / "sazmanhr" / "windows_service.py",
            )
        )
        self.assertNotIn("TLS SHA-256", active_notice_sources)

    def test_self_signed_tls_still_creates_certificate_and_key_only(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            result = ensure_self_signed_certificate(root)
            self.assertEqual(len(result), 2)
            cert, key = result
            self.assertTrue(cert.is_file())
            self.assertTrue(key.is_file())
            self.assertFalse((root / "tls" / "fingerprint.txt").exists())

    def test_legacy_fingerprint_artifacts_are_removed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            tls_dir = root / "tls"
            tls_dir.mkdir(parents=True)
            legacy = tls_dir / "fingerprint.txt"
            legacy.write_text("OLD\n", encoding="ascii")
            notice = root / "FIRST_LOGIN.txt"
            notice.write_text(
                "HRM - test\nTLS SHA-256: OLD\nUsername: admin\n",
                encoding="utf-8",
            )
            ensure_self_signed_certificate(root)
            self.assertFalse(legacy.exists())
            notice_text = notice.read_text(encoding="utf-8")
            self.assertNotIn("TLS SHA-256:", notice_text)
            self.assertIn("Username: admin", notice_text)


if __name__ == "__main__":
    unittest.main()
