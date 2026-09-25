# Regression contract: desktop client must not use certificate fingerprint pinning.
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from sazmanhr.config import ClientConfig

ROOT = Path(__file__).resolve().parents[1]


class ClientTlsNoPinningContractTests(unittest.TestCase):
    def test_client_sources_do_not_expose_or_persist_tls_fingerprints(self):
        paths = [
            ROOT / "src" / "sazmanhr" / "api_client.py",
            ROOT / "src" / "sazmanhr" / "client.py",
            ROOT / "src" / "sazmanhr" / "config.py",
            ROOT / "src" / "sazmanhr" / "ui_v49.py",
        ]
        combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)
        forbidden = (
            "tls_fingerprint",
            "remote_fingerprint",
            "certificate_fingerprint",
            "allowed_fingerprint",
            "_certificate_prompt",
            "--tls-fingerprint",
            "tls_mismatch",
            "tls_untrusted",
            "اثر انگشت TLS",
            "اثر انگشت گواهی",
        )
        for marker in forbidden:
            self.assertNotIn(marker, combined, marker)

    def test_https_remains_enabled_without_fingerprint_pinning(self):
        api = (ROOT / "src" / "sazmanhr" / "api_client.py").read_text(encoding="utf-8")
        client = (ROOT / "src" / "sazmanhr" / "client.py").read_text(encoding="utf-8")
        self.assertIn("ssl.PROTOCOL_TLS_CLIENT", api)
        self.assertIn("context.check_hostname = False", api)
        self.assertIn("context.verify_mode = ssl.CERT_NONE", api)
        self.assertIn("preflight_succeeded and same_endpoint and error.isOverridable()", client)
        self.assertNotIn("certificateChain()", client)

    def test_legacy_client_config_fingerprint_is_ignored_and_dropped_on_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "client.json"
            path.write_text(json.dumps({
                "server_url": "https://127.0.0.1:8765",
                "poll_seconds": 3,
                "tls_fingerprint": "AA:BB:CC",
            }), encoding="utf-8")
            config = ClientConfig.load(path)
            self.assertFalse(hasattr(config, "tls_fingerprint"))
            config.save(path)
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertNotIn("tls_fingerprint", saved)
            self.assertEqual(saved["server_url"], "https://127.0.0.1:8765")


if __name__ == "__main__":
    unittest.main()
