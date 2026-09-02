from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ci import validate_package_contract as validator
from tools import build_release as builder


class ManifestEolPortabilityTests(unittest.TestCase):
    def test_text_crlf_and_lf_are_identical_for_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            lf = root / "a.md"
            crlf = root / "b.md"
            lf.write_bytes(b"line1\nline2\nline3\n")
            crlf.write_bytes(b"line1\r\nline2\r\nline3\r\n")
            expected = b"line1\nline2\nline3\n"
            self.assertEqual(builder.canonical_bytes(lf), expected)
            self.assertEqual(builder.canonical_bytes(crlf), expected)
            self.assertEqual(validator.canonical_bytes(lf), expected)
            self.assertEqual(validator.canonical_bytes(crlf), expected)
            self.assertEqual(builder.digest(lf), builder.digest(crlf))
            self.assertEqual(validator.sha256_file(lf), validator.sha256_file(crlf))

    def test_binary_bytes_are_never_rewritten(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw = b"\x89PNG\r\n\x1a\n\x00binary\r\npayload"
            for name in ("sample.png", "hrm-real-data-v060b1.enc"):
                binary = root / name
                binary.write_bytes(raw)
                self.assertEqual(builder.canonical_bytes(binary), raw)
                self.assertEqual(validator.canonical_bytes(binary), raw)

    def test_builder_and_validator_use_same_canonical_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "sample.txt"
            path.write_bytes(b"a\rb\r\nc\n")
            self.assertEqual(builder.canonical_bytes(path), validator.canonical_bytes(path))


if __name__ == "__main__":
    unittest.main()
