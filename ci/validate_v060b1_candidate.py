from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

try:
    from ci.validate_v040a3_candidate import dependency_errors, pinned_requirements
except ModuleNotFoundError:
    from validate_v040a3_candidate import dependency_errors, pinned_requirements


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_VERSION = "0.6.0-beta.1"
SOURCE_REQUIREMENTS = ROOT / "ci" / "requirements-source-gates.txt"
BUILD_REQUIREMENTS = ROOT / "build" / "windows" / "requirements-build.txt"


def fail(message: str) -> None:
    print("FAIL:", message)
    raise SystemExit(1)


def source_test_environment(base: dict[str, str] | None = None) -> dict[str, str]:
    environment = dict(os.environ if base is None else base)
    paths = [str(ROOT), str(ROOT / "src")]
    inherited = environment.get("PYTHONPATH", "")
    if inherited:
        paths.append(inherited)
    environment["PYTHONPATH"] = os.pathsep.join(paths)
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
    metadata = json.loads((ROOT / "VERSION-V060B1.json").read_text(encoding="utf-8"))
    if version != EXPECTED_VERSION or metadata.get("version") != version:
        fail(f"v0.6 beta.1 metadata mismatch: VERSION={version!r}, metadata={metadata.get('version')!r}")
    if metadata.get("baseline_tag") != "v0.5.0-alpha.1":
        fail("v0.6 beta.1 must remain anchored to the tested v0.5 tag")
    if metadata.get("expected_personnel") != 1356:
        fail("approved personnel contract changed")
    if metadata.get("expected_source_assignments") != {
        "county_enrichments": 590,
        "active_named_positions": 185,
        "ignored_legacy_type_zero": 1,
    }:
        fail("approved private-source assignment contract changed")
    if metadata.get("approved_chart") != {"fixed": 536, "named": 32, "total": 568, "page_16_total": 24}:
        fail("approved chart contract changed")
    for relative in (
        "RELEASE-QUALITY-GATES.md", "ci/real_data_bundle.py",
        "ci/prepare_real_data_bundle.py", "ci/validate_v060b1_real_data.py",
        "ci/validate_overlay_integrity.py",
        "ci/stage_v060b1_overlay.py",
        "INSTALL-OVERLAY-V060B1.cmd",
        "PREPARE-REAL-DATA-V060B1.cmd", "CONFIGURE-REAL-DATA-SECRET-V060B1.cmd",
    ):
        if not (ROOT / relative).is_file():
            fail(f"pilot quality component is missing: {relative}")

    migration = subprocess.run(
        [sys.executable, str(ROOT / "ci" / "validate_v040a2_migration.py")],
        cwd=ROOT, env=source_test_environment(),
    )
    if migration.returncode:
        return migration.returncode
    regression = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=ROOT, env=source_test_environment(),
    )
    if regression.returncode:
        return regression.returncode
    print("PASS: HRM v0.6.0-beta.1 protected real-data and pilot-readiness gates passed.")
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--dependency-self-check"]:
        print("PASS: v0.6 validator direct-import contract")
        raise SystemExit(0)
    if sys.argv[1:] == ["--source-path-self-check"]:
        result = subprocess.run(
            [sys.executable, "-c", "import sazmanhr; import ci.real_data_bundle"],
            cwd=ROOT, env=source_test_environment({}), text=True, capture_output=True,
        )
        if result.returncode:
            print(result.stdout, end="")
            print(result.stderr, end="", file=sys.stderr)
            fail("clean candidate source-path contract failed")
        print("PASS: v0.6 validator clean source-path contract")
        raise SystemExit(0)
    raise SystemExit(main())
