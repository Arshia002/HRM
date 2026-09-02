#!/usr/bin/env python3
"""Verify an extracted CI overlay before its manifest can be regenerated."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ci.validate_package_contract import canonical_bytes, sha256_file  # noqa: E402


EXPECTED_PACKAGE_REVISION = "0.6.0-beta.1-ci.5"


class OverlayIntegrityError(RuntimeError):
    pass


def verify_overlay(root: Path) -> int:
    root = root.resolve()
    manifest_path = root / "PACKAGE-MANIFEST.json"
    if not manifest_path.is_file():
        raise OverlayIntegrityError("PACKAGE-MANIFEST.json is missing from the extracted overlay.")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OverlayIntegrityError("PACKAGE-MANIFEST.json is unreadable or invalid.") from exc

    revision = manifest.get("package_revision")
    if revision != EXPECTED_PACKAGE_REVISION:
        raise OverlayIntegrityError(
            f"Package revision mismatch: expected {EXPECTED_PACKAGE_REVISION}, got {revision!r}."
        )
    revision_file = root / "CI-PACKAGE-VERSION"
    if not revision_file.is_file() or revision_file.read_text(encoding="utf-8").strip() != revision:
        raise OverlayIntegrityError("CI-PACKAGE-VERSION does not match the extracted package manifest.")

    items = manifest.get("files")
    if not isinstance(items, list) or not items:
        raise OverlayIntegrityError("Package manifest contains no payload files.")
    seen: set[str] = set()
    for item in items:
        relative = item.get("path") if isinstance(item, dict) else None
        expected_bytes = item.get("bytes") if isinstance(item, dict) else None
        expected_sha = item.get("sha256") if isinstance(item, dict) else None
        if not isinstance(relative, str) or not relative:
            raise OverlayIntegrityError("Package manifest contains an invalid payload path.")
        pure = PurePosixPath(relative)
        if pure.is_absolute() or ".." in pure.parts or "\\" in relative or relative in seen:
            raise OverlayIntegrityError(f"Package manifest contains an unsafe/duplicate path: {relative!r}")
        seen.add(relative)
        target = root.joinpath(*pure.parts)
        if not target.is_file():
            raise OverlayIntegrityError(f"Extracted overlay file is missing: {relative}")
        if not isinstance(expected_bytes, int) or len(canonical_bytes(target)) != expected_bytes:
            raise OverlayIntegrityError(f"Extracted overlay byte count mismatch: {relative}")
        if not isinstance(expected_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
            raise OverlayIntegrityError(f"Package manifest has an invalid SHA-256 for: {relative}")
        if sha256_file(target) != expected_sha:
            raise OverlayIntegrityError(f"Extracted overlay SHA-256 mismatch: {relative}")
    return len(items)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        count = verify_overlay(args.root)
    except (OSError, UnicodeError, ValueError, OverlayIntegrityError) as exc:
        print(f"OVERLAY INTEGRITY ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        f"PASS: extracted {EXPECTED_PACKAGE_REVISION} overlay integrity verified "
        f"before manifest regeneration ({count} files)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
