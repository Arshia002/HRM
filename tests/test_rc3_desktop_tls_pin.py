from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / "src" / "sazmanhr" / "client.py"


class Rc3DesktopTlsNoPinTests(unittest.TestCase):
    def source(self) -> str:
        return CLIENT.read_text(encoding="utf-8")

    def test_client_source_is_valid_without_importing_pyside(self):
        ast.parse(self.source(), filename=str(CLIENT))

    def test_qt_certificate_error_is_endpoint_scoped_after_api_preflight(self):
        source = self.source()
        required = (
            "certificateError.connect(self._on_certificate_error)",
            "preflight_succeeded",
            "same_endpoint",
            "error.isOverridable()",
            "error.acceptCertificate()",
            "error.rejectCertificate()",
        )
        for marker in required:
            self.assertIn(marker, source)

    def test_leaf_certificate_fingerprint_comparison_is_absent(self):
        source = self.source()
        forbidden = (
            "certificateChain()",
            "allowed_fingerprint",
            "certificate_fingerprint",
            "_normalize_fingerprint",
            "_certificate_prompt",
            "tls_fingerprint",
        )
        for marker in forbidden:
            self.assertNotIn(marker, source, marker)

    def test_api_health_preflight_occurs_before_web_load(self):
        source = self.source()
        client = source.index("ApiClient(")
        health = source.index("client.health()", client)
        ready = source.index("self.page.preflight_succeeded = True", health)
        load = source.index("self.view.load(", ready)
        self.assertLess(client, health)
        self.assertLess(health, ready)
        self.assertLess(ready, load)


if __name__ == "__main__":
    unittest.main()
