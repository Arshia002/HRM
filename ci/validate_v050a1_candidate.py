from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

try:
    from ci.validate_v040a3_candidate import dependency_errors, pinned_requirements
except ModuleNotFoundError:  # Direct execution: python ci\validate_v050a1_candidate.py
    from validate_v040a3_candidate import dependency_errors, pinned_requirements


ROOT = Path(__file__).resolve().parents[1]
SOURCE_REQUIREMENTS = ROOT / "ci" / "requirements-source-gates.txt"
BUILD_REQUIREMENTS = ROOT / "build" / "windows" / "requirements-build.txt"
EXPECTED_VERSION = "0.5.0-alpha.1"


def fail(message: str) -> None:
    print("FAIL:", message)
    raise SystemExit(1)


def source_test_environment(base: dict[str, str] | None = None) -> dict[str, str]:
    """Return an isolated test environment that can import the src-layout package.

    The candidate validator is executed from a clean ZIP before the HRM project
    itself is installed.  Therefore it must not inherit a developer shell's
    PYTHONPATH in order to find ``src/sazmanhr``.
    """
    environment = dict(os.environ if base is None else base)
    source_path = str(ROOT / "src")
    inherited = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = (
        source_path if not inherited else source_path + os.pathsep + inherited
    )
    return environment


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
        fail("source-gate dependencies are not ready: " + "; ".join(errors))

    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    metadata = json.loads((ROOT / "VERSION-V050A1.json").read_text(encoding="utf-8"))
    if version != EXPECTED_VERSION or metadata.get("version") != version:
        fail(f"v0.5 alpha.1 metadata mismatch: VERSION={version!r}, metadata={metadata.get('version')!r}")
    if metadata.get("reference_pages") != 12 or metadata.get("client_engine") != "PySide6-native":
        fail("v0.5 alpha.1 native UI coverage metadata is incomplete")
    approved = metadata.get("approved_chart", {})
    if approved != {"fixed": 536, "named": 32, "total": 568, "page_16_total": 24}:
        fail("approved chart contract changed during UI integration")

    privacy = subprocess.run(
        [sys.executable, str(ROOT / "ci" / "validate_v040a2_migration.py")],
        cwd=ROOT,
        env=source_test_environment(),
    )
    if privacy.returncode:
        return privacy.returncode
    regression = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=ROOT,
        env=source_test_environment(),
    )
    if regression.returncode:
        return regression.returncode
    print("PASS: HRM v0.5.0-alpha.1 full native v4.9 UI candidate gates passed.")
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--dependency-self-check"]:
        print("PASS: v0.5 validator direct-import contract")
        raise SystemExit(0)
    if sys.argv[1:] == ["--source-path-self-check"]:
        check = subprocess.run(
            [sys.executable, "-c", "import sazmanhr; print(sazmanhr.__version__)"],
            cwd=ROOT,
            env=source_test_environment(),
            text=True,
            capture_output=True,
        )
        if check.returncode:
            print(check.stdout, end="")
            print(check.stderr, end="", file=sys.stderr)
            fail("clean candidate cannot import the src-layout HRM package")
        print("PASS: v0.5 validator clean source-path contract")
        raise SystemExit(0)
    raise SystemExit(main())
