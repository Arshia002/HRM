from __future__ import annotations

import importlib.metadata
import json
import subprocess
import sys
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
SOURCE_REQUIREMENTS = ROOT / "ci" / "requirements-source-gates.txt"
BUILD_REQUIREMENTS = ROOT / "build" / "windows" / "requirements-build.txt"


def fail(message: str) -> None:
    print("FAIL:", message)
    raise SystemExit(1)


def pinned_requirements(path: Path) -> dict[str, str]:
    pins: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.count("==") != 1:
            fail(f"dependency must be exactly pinned in {path.relative_to(ROOT)}: {line!r}")
        name, version = (part.strip() for part in line.split("==", 1))
        if not name or not version:
            fail(f"invalid dependency pin in {path.relative_to(ROOT)}: {line!r}")
        pins[name.lower()] = version
    if not pins:
        fail(f"no dependency pins found in {path.relative_to(ROOT)}")
    return pins


def dependency_errors(
    pins: dict[str, str],
    version_lookup: Callable[[str], str] = importlib.metadata.version,
) -> list[str]:
    errors: list[str] = []
    for name, expected in sorted(pins.items()):
        try:
            actual = version_lookup(name)
        except importlib.metadata.PackageNotFoundError:
            errors.append(f"{name} missing (expected {expected})")
            continue
        if actual != expected:
            errors.append(f"{name}=={actual} installed (expected {expected})")
    return errors


def main() -> int:
    source_pins = pinned_requirements(SOURCE_REQUIREMENTS)
    build_pins = pinned_requirements(BUILD_REQUIREMENTS)
    drift = {
        name: (expected, build_pins.get(name))
        for name, expected in source_pins.items()
        if build_pins.get(name) != expected
    }
    if drift:
        fail(f"source/build dependency pins drifted: {drift}")

    errors = dependency_errors(source_pins)
    if errors:
        command = "python -m pip install --only-binary=:all: -r ci\\requirements-source-gates.txt"
        fail("source-gate dependencies are not ready: " + "; ".join(errors) + f". Run: {command}")

    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    metadata = json.loads((ROOT / "VERSION-V040A3.json").read_text(encoding="utf-8"))
    if version != "0.4.0-alpha.3" or metadata.get("version") != version:
        fail(f"alpha.3 version metadata mismatch: VERSION={version!r}, metadata={metadata.get('version')!r}")

    result = subprocess.run([sys.executable, str(ROOT / "ci" / "validate_v040a2_migration.py")], cwd=ROOT)
    if result.returncode:
        return result.returncode
    print("PASS: HRM v0.4.0-alpha.3 clean-runner candidate gates passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
