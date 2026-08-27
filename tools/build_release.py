#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RELEASE_DIR = ROOT.parent / "release"
ARCHIVE = RELEASE_DIR / "HRM-Kermanshah-0.1.0-alpha.1-CI-Source.zip"
EXCLUDED_PARTS = {"__pycache__", "build-output", "private-data", "private", "export", ".git"}
EXCLUDED_SUFFIXES = {
    ".pyc", ".pyo", ".tmp", ".sqlite", ".db", ".xls", ".xlsx", ".xlsm",
    ".ppt", ".pptx", ".zip", ".7z", ".rar", ".key", ".pem", ".pfx", ".p12",
}
EXCLUDED_NAMES = {".env", "FIRST_LOGIN.txt", "manifest.json"}


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def source_files():
    for path in sorted(ROOT.rglob("*")):
        relative = path.relative_to(ROOT)
        if not path.is_file() or any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        if (
            path.suffix.lower() in EXCLUDED_SUFFIXES
            or path.name in EXCLUDED_NAMES
            or path.name.lower().startswith("secrets")
            or relative.as_posix() == "SHA256SUMS.txt"
        ):
            continue
        yield path, relative


def main() -> int:
    files = list(source_files())
    sums = "".join(f"{digest(path)}  {relative.as_posix()}\n" for path, relative in files)
    (ROOT / "SHA256SUMS.txt").write_text(sums, encoding="utf-8")
    files.append((ROOT / "SHA256SUMS.txt", Path("SHA256SUMS.txt")))
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE.unlink(missing_ok=True)
    with zipfile.ZipFile(ARCHIVE, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, relative in files:
            info = zipfile.ZipInfo(f"HRM-Kermanshah-0.1.0-alpha.1/{relative.as_posix()}")
            info.date_time = (2026, 8, 24, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o644 & 0xFFFF) << 16
            archive.writestr(info, path.read_bytes(), compresslevel=9)
    archive_sha = digest(ARCHIVE)
    (ARCHIVE.with_suffix(ARCHIVE.suffix + ".sha256")).write_text(
        f"{archive_sha}  {ARCHIVE.name}\n", encoding="ascii"
    )
    print(json.dumps({"archive": str(ARCHIVE), "sha256": archive_sha, "files": len(files), "bytes": ARCHIVE.stat().st_size}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
