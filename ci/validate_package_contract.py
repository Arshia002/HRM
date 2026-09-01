#!/usr/bin/env python3
"""Fail-fast validation for the HRM Windows packaging contract.

The v0.5 candidate preserves the clean-checkout boundary established by
alpha.3 and adds a complete native v4.9 page-coverage contract.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path, PurePosixPath

PROJECT = Path(__file__).resolve().parents[1]
EXPECTED_VERSION = "0.5.0-alpha.1"
EXPECTED_EXES = {
    "client.spec": "HRM",
    "server.spec": "HRMServer",
    "service.spec": "HRMService",
    "migration.spec": "HRMMigration",
}
INNO = PROJECT / "build" / "windows" / "HRM.iss"
PACKAGE_MANIFEST = PROJECT / "PACKAGE-MANIFEST.json"
EPHEMERAL_PARTS = {
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".nox",
    ".venv", "venv", "__pycache__", "build-output", ".git",
}
EPHEMERAL_NAMES = {".coverage", "coverage.xml"}


def fail(message: str) -> None:
    raise RuntimeError(message)


# HRM_MANIFEST_CANONICAL_LF_V1
BINARY_SUFFIXES = {'.ico', '.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.sqlite', '.db', '.zip', '.exe', '.dll', '.pyd', '.so', '.pdf', '.xls', '.xlsx', '.ppt', '.pptx', '.doc', '.docx', '.woff', '.woff2', '.ttf', '.otf'}

def canonical_bytes(path: Path) -> bytes:
    # Git clean checkouts normalize text to LF. Windows working trees may
    # expose CRLF, so manifest hashing must canonicalize text bytes.
    raw = path.read_bytes()
    if path.suffix.lower() in BINARY_SUFFIXES or b"\x00" in raw:
        return raw
    return raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")

def sha256_file(path: Path) -> str:
    return hashlib.sha256(canonical_bytes(path)).hexdigest()

def exe_name_from_spec(path: Path) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Name) and func.id == "EXE"):
            continue
        for keyword in node.keywords:
            if keyword.arg == "name" and isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
                found.append(keyword.value.value)
    if len(found) != 1:
        fail(f"Expected exactly one EXE(name=...) in {path.name}; found {found!r}")
    return found[0]


def validate_specs() -> None:
    for spec_name, expected in EXPECTED_EXES.items():
        path = PROJECT / "build" / "windows" / spec_name
        if not path.is_file():
            fail(f"Missing PyInstaller spec: {path}")
        actual = exe_name_from_spec(path)
        if actual != expected:
            fail(
                f"PyInstaller contract mismatch in {spec_name}: EXE name is {actual!r}, "
                f"but build/installer expects {expected!r}.exe"
            )
        print(f"PASS spec output: {spec_name} -> {expected}.exe")


def validate_inno_sources() -> None:
    if not INNO.is_file():
        fail(f"Missing Inno Setup script: {INNO}")
    script = INNO.read_text(encoding="utf-8")
    lowered = script.lower()
    for exe in ("HRM.exe", "HRMServer.exe", "HRMService.exe", "HRMMigration.exe"):
        if exe.lower() not in lowered:
            fail(f"Inno Setup does not reference required frozen executable: {exe}")
    if "sazmanhr.exe" in lowered:
        fail("Legacy client executable name SazmanHR.exe is still referenced by Inno Setup")

    # ProjectRoot sources are repository files and must be ASCII-safe so ZIP ->
    # Windows extraction cannot rewrite their names. DistDir is generated in CI.
    pattern = re.compile(r'^Source:\s*"\{#ProjectRoot\}\\([^\"]+)"', re.MULTILINE)
    sources = pattern.findall(script)
    if not sources:
        fail("No {#ProjectRoot} sources were found in the Inno Setup [Files] section")
    for raw in sources:
        try:
            raw.encode("ascii")
        except UnicodeEncodeError:
            fail(f"Inno source path must be ASCII-safe: {raw!r}")
        path = PROJECT.joinpath(*raw.split("\\"))
        if not path.is_file():
            fail(f"Inno Setup source does not exist: {raw} -> {path}")
        print(f"PASS Inno source exists: {raw}")

    # Regression gates restored from the proven alpha.4 baseline.
    required_markers = (
        "service-stop-before-copy",
        "--stop-windows-service HRMCentralService",
        "HRMCentralService",
        'obj= "NT AUTHORITY\\LocalService"',
        "sidtype HRMCentralService unrestricted",
    )
    for marker in required_markers:
        if marker.lower() not in lowered:
            fail(f"Proven upgrade/service hardening marker is missing from HRM.iss: {marker!r}")
    if "hrmcentral " in lowered and "hrmcentralservice" not in lowered:
        fail("Legacy alpha.2 service name HRMCentral would break alpha.4 upgrade compatibility")
    print("PASS proven alpha.4 upgrade/service baseline markers")


def validate_builder_contract() -> None:
    builder = (PROJECT / "build" / "windows" / "build_windows.py").read_text(encoding="utf-8")
    if '"HRM.iss"' not in builder:
        fail("build_windows.py is not wired to build/windows/HRM.iss")
    for exe in ("HRM.exe", "HRMServer.exe", "HRMService.exe", "HRMMigration.exe"):
        if exe not in builder:
            fail(f"Builder does not validate expected output {exe}")
    if '"--smoke-test"' not in builder:
        fail("Builder no longer smoke-tests the frozen Qt client before compiling Setup")
    if '"--ui-smoke-test"' not in builder:
        fail("Builder does not construct the frozen native login/dashboard shell before Setup")
    if "--only-binary=:all:" not in builder:
        fail("Windows dependency install must be wheel-only for reproducible CI")
    if '"HRMMigration.exe", "--self-test"' not in builder:
        fail("Builder does not smoke-test the frozen migration runtime")
    print("PASS builder executable/runtime contract")


def validate_branding_contract() -> None:
    client = (PROJECT / "src" / "sazmanhr" / "client.py").read_text(encoding="utf-8")
    pages = (PROJECT / "src" / "sazmanhr" / "ui_v49.py").read_text(encoding="utf-8")
    branding = (PROJECT / "src" / "sazmanhr" / "branding.py").read_text(encoding="utf-8")
    client_spec = (PROJECT / "build" / "windows" / "client.spec").read_text(encoding="utf-8")
    required = ("brandPanel", "loginPanel", "topbar", "connectionBadge", "--ui-smoke-test", "COMPANY_NAME")
    for item in required:
        if item not in client:
            fail(f"Native v4.9 shell branding marker missing from client.py: {item}")
    if 'assets" / "HRM.png"' not in client_spec:
        fail("client.spec does not bundle assets/HRM.png for frozen native branding")
    for relative in ("assets/HRM.png", "assets/HRM.ico", "assets/company-logo-source.png"):
        path = PROJECT / relative
        if not path.is_file() or path.stat().st_size < 100:
            fail(f"Brand asset missing or invalid: {relative}")
    if 'COMPANY_NAME = "شرکت توزیع نیروی برق استان کرمانشاه"' not in branding:
        fail("Official company branding constant is missing")
    for page_key in (
        "formalChart", "statusChart", "personnelDirectory", "personnelEducation",
        "jobFamilies", "personnelAge", "reports", "imports", "users", "history",
        "systemHealth", "settings",
    ):
        if f'"{page_key}"' not in client + pages:
            fail(f"Native v4.9 reference page is missing: {page_key}")
    for page_class in (
        "StatusChartPage", "PersonnelEducationPage", "PersonnelStatusPage",
        "PersonnelAgePage", "ReportsPage", "ImportPage", "UsersPage",
        "HistoryBackupPage", "SystemHealthPage", "SettingsPage",
    ):
        if f"class {page_class}" not in pages or f"{page_class}(self)" not in client:
            fail(f"Native v4.9 page is not wired into the client: {page_class}")
    lowered = (client + pages).lower()
    for forbidden in ("qtwebengine", "qwebengine", "chromium", "electron"):
        if forbidden in lowered:
            fail(f"Native client contains forbidden browser-runtime marker: {forbidden}")
    if "set(V49_REFERENCE_PAGES) - set(window.page_keys)" not in client:
        fail("Frozen native UI smoke does not enforce complete v4.9 page coverage")
    print("PASS full native v4.9 shell, page coverage and HRM branding contract")


def validate_versions() -> None:
    version = (PROJECT / "VERSION").read_text(encoding="utf-8").strip()
    if version != EXPECTED_VERSION:
        fail(f"VERSION mismatch: expected {EXPECTED_VERSION!r}, got {version!r}")
    checks = {
        "src/sazmanhr/__init__.py": f'__version__ = "{EXPECTED_VERSION}"',
        "build/windows/HRM.iss": f"AppVersion={EXPECTED_VERSION}",
        "build/windows/smoke-install.ps1": EXPECTED_VERSION,
        "ci/write-ci-manifest.ps1": f"version = '{EXPECTED_VERSION}'",
        ".github/workflows/windows-build.yml": f"HRM-{EXPECTED_VERSION}-Tested-Setup",
    }
    for relative, marker in checks.items():
        text = (PROJECT / relative).read_text(encoding="utf-8")
        if marker not in text:
            fail(f"Version contract missing in {relative}: {marker!r}")
    print(f"PASS version contract: {EXPECTED_VERSION}")


def load_manifest_items() -> list[dict[str, object]]:
    if not PACKAGE_MANIFEST.is_file():
        fail(f"Missing package manifest: {PACKAGE_MANIFEST}")
    manifest = json.loads(PACKAGE_MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("version") != EXPECTED_VERSION:
        fail(f"PACKAGE-MANIFEST version mismatch: {manifest.get('version')!r}")
    items = manifest.get("files")
    if not isinstance(items, list) or not items:
        fail("PACKAGE-MANIFEST.json has no files list")
    return items


def validate_package_manifest_paths() -> list[str]:
    """Validate the exact CI overlay boundary, never the whole worktree."""
    items = load_manifest_items()
    bad: list[str] = []
    missing: list[str] = []
    unsafe: list[str] = []
    ephemeral: list[str] = []
    seen: set[str] = set()
    paths: list[str] = []
    for item in items:
        relative = item.get("path") if isinstance(item, dict) else None
        if not isinstance(relative, str) or not relative:
            fail(f"Invalid package manifest item: {item!r}")
        if relative in seen:
            fail(f"Duplicate package manifest path: {relative}")
        seen.add(relative)
        paths.append(relative)
        try:
            relative.encode("ascii")
        except UnicodeEncodeError:
            bad.append(relative)
            continue
        pure = PurePosixPath(relative)
        if pure.is_absolute() or ".." in pure.parts or "\\" in relative:
            unsafe.append(relative)
            continue
        if any(part in EPHEMERAL_PARTS for part in pure.parts) or pure.name in EPHEMERAL_NAMES:
            ephemeral.append(relative)
            continue
        path = PROJECT.joinpath(*pure.parts)
        if not path.is_file():
            missing.append(relative)
            continue
        expected_bytes = item.get("bytes") if isinstance(item, dict) else None
        expected_sha = item.get("sha256") if isinstance(item, dict) else None
        if not isinstance(expected_bytes, int) or expected_bytes < 0:
            fail(f"Invalid byte count in package manifest for {relative}: {expected_bytes!r}")
        if not isinstance(expected_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
            fail(f"Invalid SHA-256 in package manifest for {relative}: {expected_sha!r}")
        actual_bytes = len(canonical_bytes(path))
        if actual_bytes != expected_bytes:
            fail(f"Package manifest byte mismatch for {relative}: expected {expected_bytes}, got {actual_bytes}")
        actual_sha = sha256_file(path)
        if actual_sha != expected_sha:
            fail(f"Package manifest SHA-256 mismatch for {relative}: expected {expected_sha}, got {actual_sha}")
    if bad:
        fail(f"Non-ASCII paths declared in CI package manifest: {bad}")
    if unsafe:
        fail(f"Unsafe paths declared in CI package manifest: {unsafe}")
    if ephemeral:
        fail(f"Ephemeral/local-only files must never be declared in CI package manifest: {ephemeral}")
    if missing:
        fail(f"Files declared in CI package manifest are missing after overlay: {missing}")
    print(f"PASS CI overlay manifest paths/hashes are stable and present: {len(items)} files")
    return paths


def validate_git_tracking(paths: list[str], require: bool) -> None:
    if not require:
        return
    try:
        raw = subprocess.check_output(
            ["git", "ls-files", "-z"], cwd=PROJECT, stderr=subprocess.STDOUT
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        fail(f"Git tracking verification could not run: {exc}")
    tracked = {item.decode("utf-8") for item in raw.split(b"\0") if item}
    untracked = [relative for relative in paths if relative not in tracked]
    if untracked:
        fail(
            "CI package manifest contains files absent from the Git index/clean checkout: "
            f"{untracked}"
        )
    print(f"PASS clean-checkout tracking contract: {len(paths)} manifest files are in Git")


def validate_public_safe_seed() -> None:
    export_dir = PROJECT / "data" / "export"
    if export_dir.exists():
        fail("data/export must not be present in a public CI package")
    for pattern in ("*.xls", "*.xlsx", "*.csv"):
        matches = [p for p in PROJECT.rglob(pattern) if p.is_file() and ".git" not in p.parts]
        if matches:
            fail(f"Public CI package contains forbidden data file(s): {matches}")

    manifest_path = PROJECT / "data" / "seed" / "manifest.json"
    database = PROJECT / "data" / "seed" / "sazmanhr-seed.sqlite"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("contains_real_personnel") is not False:
        fail("Seed manifest must explicitly set contains_real_personnel=false")
    if manifest.get("contains_real_organization_chart") is not False:
        fail("Seed manifest must explicitly set contains_real_organization_chart=false")
    with sqlite3.connect(database) as conn:
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            fail("Synthetic seed failed SQLite integrity_check")
        personnel = conn.execute("SELECT COUNT(*) FROM personnel").fetchone()[0]
    if personnel != 36:
        fail(f"Synthetic seed personnel count changed unexpectedly: {personnel}")
    print("PASS public-safe synthetic seed: 36 demo personnel")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--require-git-tracked",
        action="store_true",
        help="Require every manifest file to exist in Git's index (clean-checkout CI gate).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    require_tracking = args.require_git_tracked or os.environ.get("GITHUB_ACTIONS", "").lower() == "true"
    try:
        validate_specs()
        validate_inno_sources()
        validate_builder_contract()
        validate_branding_contract()
        validate_versions()
        paths = validate_package_manifest_paths()
        validate_git_tracking(paths, require_tracking)
        validate_public_safe_seed()
    except Exception as exc:
        print(f"PACKAGE CONTRACT ERROR: {exc}", file=sys.stderr)
        return 1
    print("ALL PACKAGE CONTRACT CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
