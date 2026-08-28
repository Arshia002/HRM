#!/usr/bin/env python3
"""Fail-fast validation for the HRM Windows packaging contract.

The validator deliberately checks *packaging inputs*, not every file already
tracked by the repository. The repository contains historical Persian-named
Markdown documents that are not part of the Windows installer/CI payload.
Rejecting those unrelated files caused the alpha.2 pre-push false positive.
"""
from __future__ import annotations

import ast
import json
import re
import sqlite3
import sys
from pathlib import Path, PurePosixPath

PROJECT = Path(__file__).resolve().parents[1]
EXPECTED_EXES = {
    "client.spec": "HRM",
    "server.spec": "HRMServer",
    "service.spec": "HRMService",
}
INNO = PROJECT / "build" / "windows" / "HRM.iss"
PACKAGE_MANIFEST = PROJECT / "PACKAGE-MANIFEST.json"


def fail(message: str) -> None:
    raise RuntimeError(message)


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
    for exe in ("HRM.exe", "HRMServer.exe", "HRMService.exe"):
        if exe.lower() not in lowered:
            fail(f"Inno Setup does not reference required frozen executable: {exe}")
    if "sazmanhr.exe" in lowered:
        fail("Legacy client executable name SazmanHR.exe is still referenced by Inno Setup")

    # Only installer payload paths need the ASCII ZIP/Windows-path guarantee.
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


def validate_builder_contract() -> None:
    builder = (PROJECT / "build" / "windows" / "build_windows.py").read_text(encoding="utf-8")
    if '"HRM.iss"' not in builder:
        fail("build_windows.py is not wired to build/windows/HRM.iss")
    for exe in ("HRM.exe", "HRMServer.exe", "HRMService.exe"):
        if exe not in builder:
            fail(f"Builder does not validate expected output {exe}")
    print("PASS builder executable contract")


def validate_versions() -> None:
    version = (PROJECT / "VERSION").read_text(encoding="utf-8").strip()
    expected = "0.2.0-alpha.2"
    if version != expected:
        fail(f"VERSION mismatch: expected {expected!r}, got {version!r}")
    checks = {
        "src/sazmanhr/__init__.py": f'__version__ = "{expected}"',
        "build/windows/HRM.iss": f"AppVersion={expected}",
        "build/windows/smoke-install.ps1": f"version -ne '{expected}'",
        "ci/write-ci-manifest.ps1": f"version = '{expected}'",
        ".github/workflows/windows-build.yml": f"HRM-{expected}-Tested-Setup",
    }
    for relative, marker in checks.items():
        text = (PROJECT / relative).read_text(encoding="utf-8")
        if marker not in text:
            fail(f"Version contract missing in {relative}: {marker!r}")
    print(f"PASS version contract: {expected}")


def validate_package_manifest_paths() -> None:
    """Validate only files declared as part of this CI overlay package.

    Existing repository files that are not installer/build inputs may use
    Unicode names. This keeps the ZIP/Windows contract strict without making
    unrelated documentation a build blocker.
    """
    if not PACKAGE_MANIFEST.is_file():
        fail(f"Missing package manifest: {PACKAGE_MANIFEST}")
    manifest = json.loads(PACKAGE_MANIFEST.read_text(encoding="utf-8"))
    items = manifest.get("files")
    if not isinstance(items, list) or not items:
        fail("PACKAGE-MANIFEST.json has no files list")

    bad: list[str] = []
    missing: list[str] = []
    unsafe: list[str] = []
    seen: set[str] = set()
    for item in items:
        relative = item.get("path") if isinstance(item, dict) else None
        if not isinstance(relative, str) or not relative:
            fail(f"Invalid package manifest item: {item!r}")
        if relative in seen:
            fail(f"Duplicate package manifest path: {relative}")
        seen.add(relative)
        try:
            relative.encode("ascii")
        except UnicodeEncodeError:
            bad.append(relative)
            continue
        pure = PurePosixPath(relative)
        if pure.is_absolute() or ".." in pure.parts or "\\" in relative:
            unsafe.append(relative)
            continue
        path = PROJECT.joinpath(*pure.parts)
        if not path.is_file():
            missing.append(relative)
    if bad:
        fail(f"Non-ASCII paths declared in CI package manifest: {bad}")
    if unsafe:
        fail(f"Unsafe paths declared in CI package manifest: {unsafe}")
    if missing:
        fail(f"Files declared in CI package manifest are missing after overlay: {missing}")
    print(f"PASS CI overlay manifest paths are ASCII-safe: {len(items)} files")


def validate_public_safe_seed() -> None:
    export_dir = PROJECT / "data" / "export"
    if export_dir.exists():
        fail("data/export must not be present in a public CI package")
    for pattern in ("*.xls", "*.xlsx", "*.csv"):
        matches = [p for p in PROJECT.rglob(pattern) if p.is_file()]
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


def main() -> int:
    try:
        validate_specs()
        validate_inno_sources()
        validate_builder_contract()
        validate_versions()
        validate_package_manifest_paths()
        validate_public_safe_seed()
    except Exception as exc:
        print(f"PACKAGE CONTRACT ERROR: {exc}", file=sys.stderr)
        return 1
    print("ALL PACKAGE CONTRACT CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
