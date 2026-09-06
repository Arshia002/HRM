#!/usr/bin/env python3
"""Validate staged whitespace without mutating immutable v4.9 reference assets.

The exact SazmanHR v4.9 `web/assets/app.js` contains intentional trailing
whitespace in the upstream/reference bytes.  Trimming it would break the
byte-for-byte UI identity contract.  We therefore exempt only that one path
from Git's whitespace checker, and only while its SHA-256 remains exactly the
locked v4.9 reference digest.  Every other staged path is checked normally.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXACT_REFERENCE_EXEMPTIONS = {
    "web/assets/app.js": "d65eebcb8e807effe84c856e35c7a96778773cbb7ea33e753a997e8adf4d9070",
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fail(message: str) -> int:
    print(f"STAGED DIFF ERROR: {message}", file=sys.stderr)
    return 1


def main() -> int:
    for relative, expected in EXACT_REFERENCE_EXEMPTIONS.items():
        path = ROOT / relative
        if not path.is_file():
            return fail(f"immutable v4.9 reference asset is missing: {relative}")
        actual = sha256_file(path)
        if actual != expected:
            return fail(
                f"immutable v4.9 reference asset hash mismatch: {relative}; "
                f"expected {expected}, got {actual}"
            )

    command = ["git", "diff", "--cached", "--check", "--", "."]
    command.extend(f":(exclude){relative}" for relative in EXACT_REFERENCE_EXEMPTIONS)
    result = subprocess.run(command, cwd=ROOT, check=False)
    if result.returncode != 0:
        return fail("staged whitespace check failed outside the locked v4.9 reference exemption")

    print(
        "PASS: staged whitespace check passed; exact v4.9 app.js is exempt only "
        "under immutable SHA-256 lock."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
