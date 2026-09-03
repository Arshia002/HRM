#!/usr/bin/env python3
"""Stage only the validated v0.6 package overlay, never unrelated worktree files."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "PACKAGE-MANIFEST.json"


def fail(message: str) -> None:
    raise RuntimeError(message)


def allowed_paths() -> list[str]:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    items = payload.get("files")
    if not isinstance(items, list) or not items:
        fail("Package manifest has no stageable files.")
    paths: list[str] = []
    for item in items:
        relative = item.get("path") if isinstance(item, dict) else None
        if not isinstance(relative, str):
            fail("Package manifest contains an invalid path.")
        pure = PurePosixPath(relative)
        if pure.is_absolute() or ".." in pure.parts or "\\" in relative:
            fail(f"Unsafe package path cannot be staged: {relative!r}")
        paths.append(relative)
    paths.extend(("PACKAGE-MANIFEST.json", "SHA256SUMS.txt"))
    if len(paths) != len(set(paths)):
        fail("Package stage path set contains duplicates.")
    return sorted(paths)


def main() -> int:
    try:
        paths = allowed_paths()
        staged_before = subprocess.run(
            ["git", "diff", "--cached", "--quiet"], cwd=ROOT, check=False
        )
        if staged_before.returncode != 0:
            fail("Git index already contains changes; unstage them before guarded push.")
        for start in range(0, len(paths), 40):
            subprocess.run(
                ["git", "add", "--", *paths[start:start + 40]], cwd=ROOT, check=True
            )
        raw = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only", "-z"], cwd=ROOT
        )
        staged = {part.decode("utf-8") for part in raw.split(b"\0") if part}
        unexpected = sorted(staged - set(paths))
        if unexpected:
            fail(f"Guarded stage contains paths outside the package manifest: {unexpected}")
        if not staged:
            fail("No package changes were staged.")
    except (OSError, subprocess.CalledProcessError, RuntimeError, ValueError) as exc:
        print(f"STAGE ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"PASS: staged {len(staged)} changed overlay file(s); unrelated files remain unstaged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
