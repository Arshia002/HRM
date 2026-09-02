#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE_DIR = ROOT.parent / "release"
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
PACKAGE_REVISION = (ROOT / "CI-PACKAGE-VERSION").read_text(encoding="utf-8").strip()
PACKAGE_DIR_NAME = f"HRM-v{PACKAGE_REVISION}-CI-Build-Package"
ARCHIVE = RELEASE_DIR / f"{PACKAGE_DIR_NAME}.zip"

# Only stable source/package inputs may enter the public CI overlay. In
# particular, never derive the package boundary from an unrestricted rglob of
# a developer worktree: alpha.2 proved that local .pytest_cache files can then
# leak into PACKAGE-MANIFEST.json even though Git ignores them.
EXCLUDED_PARTS = {
    ".git", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".nox",
    ".venv", "venv", "__pycache__", "build-output", "release",
}
EXCLUDED_NAMES = {"PACKAGE-MANIFEST.json", "SHA256SUMS.txt", ".coverage", "coverage.xml"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".tmp", ".log"}
ROOT_FILES = {
    ".gitattributes", ".gitignore", "BUILD-SETUP.cmd", "CHANGELOG.md",
    "CI-LOCAL-VALIDATION.md", "CI-PACKAGE-VERSION", "CI-README-FA.md",
    "HRM-V030A2-NOTES.md", "LICENSE.txt", "PUSH-TO-GITHUB.cmd", "README.md",
    "ROOT-CAUSE-alpha1.md", "ROOT-CAUSE-alpha2-prepush.md", "ROOT-CAUSE-alpha2-ci.md",
    "TEST-REPORT-HRM-v0.3.0-alpha.2.md", "TEST-REPORT.md", "VERSION", "pyproject.toml",
    "APPLY-V030A2.cmd", "APPLY-V040A1.cmd", "README-V040A1.txt",
    "RUN-DRY-RUN-V040A1.cmd", "TEST-REPORT-V040A1.txt", "VERSION-V040A1.json",
    "APPLY-V040A2.cmd", "README-V040A2.txt", "RUN-MIGRATION-V040A2.cmd",
    "TEST-REPORT-V040A2.txt", "VERSION-V040A2.json",
    "APPLY-V040A3.cmd", "README-V040A3.txt", "RUN-MIGRATION-V040A3.cmd",
    "TEST-REPORT-V040A3.txt", "VERSION-V040A3.json",
    "APPLY-V050A1.cmd", "README-V050A1.txt", "TEST-REPORT-V050A1.txt", "VERSION-V050A1.json",
    "APPLY-V060B1.cmd", "CONFIGURE-REAL-DATA-SECRET-V060B1.cmd",
    "PREPARE-REAL-DATA-V060B1.cmd", "README-V060B1.txt",
    "RELEASE-QUALITY-GATES.md", "TEST-REPORT-V060B1.txt", "VERSION-V060B1.json",
}
ALLOWED_DIRS = {".github", "assets", "build", "ci", "data", "docs", "scripts", "src", "tests", "tools", "test-evidence"}


# HRM_MANIFEST_CANONICAL_LF_V1
BINARY_SUFFIXES = {'.ico', '.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.sqlite', '.db', '.zip', '.enc', '.exe', '.dll', '.pyd', '.so', '.pdf', '.xls', '.xlsx', '.ppt', '.pptx', '.doc', '.docx', '.woff', '.woff2', '.ttf', '.otf'}

def canonical_bytes(path: Path) -> bytes:
    # Git clean checkouts normalize text to LF. Windows working trees may
    # expose CRLF, so manifest hashing must canonicalize text bytes.
    raw = path.read_bytes()
    if path.suffix.lower() in BINARY_SUFFIXES or b"\x00" in raw:
        return raw
    return raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")

def digest(path: Path) -> str:
    return hashlib.sha256(canonical_bytes(path)).hexdigest()

def is_stable_overlay_file(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    if not path.is_file():
        return False
    if relative.name in EXCLUDED_NAMES or path.suffix.lower() in EXCLUDED_SUFFIXES:
        return False
    if any(part in EXCLUDED_PARTS for part in relative.parts):
        return False
    if len(relative.parts) == 1:
        return relative.as_posix() in ROOT_FILES
    if relative.parts[0] not in ALLOWED_DIRS:
        return False
    # Private/exported datasets are never valid public overlay input.
    if relative.parts[:2] == ("data", "export"):
        return False
    if path.suffix.lower() in {".xls", ".xlsx", ".csv"}:
        return False
    # The overlay itself is intentionally ASCII-path-safe. Existing historical
    # Unicode documents in the repository are outside this boundary.
    try:
        relative.as_posix().encode("ascii")
    except UnicodeEncodeError:
        return False
    return True


def payload_files() -> list[tuple[Path, Path]]:
    files: list[tuple[Path, Path]] = []
    for path in sorted(ROOT.rglob("*")):
        if is_stable_overlay_file(path):
            files.append((path, path.relative_to(ROOT)))
    return files


def write_manifest(files: list[tuple[Path, Path]]) -> Path:
    manifest = {
        "manifest_schema": 4,
        "product": "HRM",
        "version": VERSION,
        "package_revision": PACKAGE_REVISION,
        "purpose": "github-windows-ci-clean-checkout-candidate",
        "contains_plaintext_real_data": False,
        "contains_encrypted_real_data_bundle": any(
            relative.as_posix() == "ci/real-data/hrm-real-data-v060b1.enc"
            for _, relative in files
        ),
        "real_data_artifact_policy": "aggregate-only",
        "expected_windows_artifact": f"HRM-{VERSION}-Tested-Setup",
        "files": [
            {
                "path": relative.as_posix(),
                "bytes": len(canonical_bytes(path)),
                "sha256": digest(path),
            }
            for path, relative in files
        ],
    }
    target = ROOT / "PACKAGE-MANIFEST.json"
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return target


def main() -> int:
    files = payload_files()
    if not files:
        raise SystemExit("No stable overlay files were selected.")

    manifest_path = write_manifest(files)
    package_files = [*files, (manifest_path, Path("PACKAGE-MANIFEST.json"))]

    sums = "".join(f"{digest(path)}  {relative.as_posix()}\n" for path, relative in package_files)
    sums_path = ROOT / "SHA256SUMS.txt"
    sums_path.write_text(sums, encoding="utf-8", newline="\n")
    package_files.append((sums_path, Path("SHA256SUMS.txt")))

    RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE.unlink(missing_ok=True)
    with zipfile.ZipFile(ARCHIVE, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, relative in package_files:
            info = zipfile.ZipInfo(f"{PACKAGE_DIR_NAME}/{relative.as_posix()}")
            info.date_time = (2026, 8, 28, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o644 & 0xFFFF) << 16
            archive.writestr(info, canonical_bytes(path), compresslevel=9)

    archive_sha = digest(ARCHIVE)
    (ARCHIVE.with_suffix(ARCHIVE.suffix + ".sha256")).write_text(
        f"{archive_sha}  {ARCHIVE.name}\n", encoding="ascii"
    )
    print(json.dumps({
        "archive": str(ARCHIVE),
        "sha256": archive_sha,
        "payload_files": len(files),
        "archive_files": len(package_files),
        "bytes": ARCHIVE.stat().st_size,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
