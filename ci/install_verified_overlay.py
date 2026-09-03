#!/usr/bin/env python3
"""Install a verified HRM overlay by manifest, without timestamp/size heuristics."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
from pathlib import Path, PurePosixPath

BINARY_SUFFIXES = {'.ico', '.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.sqlite', '.db', '.zip', '.enc', '.exe', '.dll', '.pyd', '.so', '.pdf', '.xls', '.xlsx', '.ppt', '.pptx', '.doc', '.docx', '.woff', '.woff2', '.ttf', '.otf'}


def canonical_bytes(path: Path) -> bytes:
    raw = path.read_bytes()
    if path.suffix.lower() in BINARY_SUFFIXES or b"\x00" in raw:
        return raw
    return raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(canonical_bytes(path)).hexdigest()


def fail(message: str) -> None:
    raise RuntimeError(message)


def safe_target(root: Path, relative: str) -> Path:
    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts or "\\" in relative:
        fail(f"Unsafe manifest path: {relative!r}")
    target = root.joinpath(*pure.parts)
    try:
        target.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise RuntimeError(f"Manifest path escapes target root: {relative!r}") from exc
    return target


def make_writable(path: Path) -> None:
    if path.exists():
        try:
            os.chmod(path, stat.S_IREAD | stat.S_IWRITE)
        except OSError:
            pass


def install(source: Path, target: Path) -> int:
    source = source.resolve()
    target = target.resolve()
    manifest_path = source / "PACKAGE-MANIFEST.json"
    sums_path = source / "SHA256SUMS.txt"
    if not manifest_path.is_file() or not sums_path.is_file():
        fail("Source package metadata is incomplete.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    items = manifest.get("files")
    if not isinstance(items, list) or not items:
        fail("Source package manifest contains no payload files.")

    seen: set[str] = set()
    copied = 0
    for item in items:
        if not isinstance(item, dict):
            fail("Invalid manifest item.")
        relative = item.get("path")
        expected_bytes = item.get("bytes")
        expected_sha = item.get("sha256")
        if not isinstance(relative, str) or not relative or relative in seen:
            fail(f"Invalid/duplicate manifest path: {relative!r}")
        seen.add(relative)
        if not isinstance(expected_bytes, int):
            fail(f"Invalid manifest byte count: {relative}")
        if not isinstance(expected_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
            fail(f"Invalid manifest SHA-256: {relative}")

        src = safe_target(source, relative)
        dst = safe_target(target, relative)
        if not src.is_file():
            fail(f"Source payload file is missing: {relative}")
        if len(canonical_bytes(src)) != expected_bytes or sha256_file(src) != expected_sha:
            fail(f"Source payload changed after package validation: {relative}")

        dst.parent.mkdir(parents=True, exist_ok=True)
        make_writable(dst)
        shutil.copyfile(src, dst)
        if len(canonical_bytes(dst)) != expected_bytes or sha256_file(dst) != expected_sha:
            fail(f"Installed payload verification failed: {relative}")
        copied += 1

    # Metadata is intentionally copied after the payload. It is not part of
    # manifest[files], so it cannot make the payload manifest self-referential.
    for name in ("PACKAGE-MANIFEST.json", "SHA256SUMS.txt"):
        src = source / name
        dst = target / name
        make_writable(dst)
        shutil.copyfile(src, dst)
        if src.read_bytes() != dst.read_bytes():
            fail(f"Installed package metadata verification failed: {name}")

    return copied


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    args = parser.parse_args()
    try:
        count = install(args.source, args.target)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError, RuntimeError) as exc:
        print(f"MANIFEST INSTALL ERROR: {exc}")
        return 1
    print(f"PASS: manifest-driven overlay copied and verified ({count} payload files).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
