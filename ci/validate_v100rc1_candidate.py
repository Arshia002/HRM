from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

try:
    from ci.release_identity import load_identity
    from ci.validate_v040a3_candidate import dependency_errors, pinned_requirements
except ModuleNotFoundError:
    from release_identity import load_identity
    from validate_v040a3_candidate import dependency_errors, pinned_requirements

ROOT = Path(__file__).resolve().parents[1]
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
    identity = load_identity()
    source_pins = pinned_requirements(SOURCE_REQUIREMENTS)
    build_pins = pinned_requirements(BUILD_REQUIREMENTS)
    drift = {name: (expected, build_pins.get(name)) for name, expected in source_pins.items()
             if build_pins.get(name) != expected}
    if drift:
        fail(f"source/build dependency pins drifted: {drift}")
    errors = dependency_errors(source_pins)
    if errors:
        fail("source-gate dependencies are not ready: " + "; ".join(errors))

    metadata = identity.metadata
    if identity.version != "1.0.0-rc.1" or identity.package_revision != "1.0.0-rc.1-ci.2":
        fail("RC identity is not the approved v1.0 rc.1 ci.2 release identity")
    if identity.baseline_commit != "8f1adfa88a1b53db1b075504c58900957e812894":
        fail("v1.0 RC must remain anchored to the tested v0.8 source revision")
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

    deployment = metadata.get("deployment_profile")
    if not isinstance(deployment, dict) or deployment.get("roles") != {"super_admin": 2, "hr_admin": 4}:
        fail("final organizational role profile changed")
    if deployment.get("server_os") != "Windows Server 2022" or deployment.get("internet_dependency") is not False:
        fail("final deployment profile changed")
    backup_policy = metadata.get("backup_policy")
    if not isinstance(backup_policy, dict) or backup_policy.get("interval_hours") != 24 or backup_policy.get("local_retention") != 30:
        fail("final backup policy changed")
    if backup_policy.get("secondary_destination_supported") is not True:
        fail("secondary backup support is required for final candidate")

    required = (
        "RELEASE-QUALITY-GATES.md",
        "ci/release_identity.py",
        "ci/real_data_bundle.py",
        "ci/validate_v060b1_real_data.py",
        "ci/validate_overlay_integrity.py",
        "ci/install_verified_overlay.py",
        "ci/validate_rc_hardening.py",
        "ci/stage_v100rc1_overlay.py",
        "INSTALL-OVERLAY-V100RC1.cmd",
        "build/windows/smoke-upgrade-from-v080.ps1",
        "tools/collect-diagnostics.ps1",
        "tests/test_rc_network_resilience.py",
        "tests/test_rc_disaster_recovery.py",
        "tests/test_rc_release_identity.py",
        "tests/test_v080rc1_movements.py",
        "tests/test_v100rc1_operations.py",
        "ci/cleanup_v100rc1_repository.py",
        "docs/V100RC1-FINAL-PRODUCTION-CANDIDATE.md",
        "docs/production-deployment-checklist-fa.md",
        "docs/production-operations-fa.md",
        "deploy/linux-web-test/docker-compose.yml",
        "web/index.html",
    )
    for relative in required:
        if not (ROOT / relative).is_file():
            fail(f"RC quality component is missing: {relative}")

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
    print("PASS: HRM v1.0.0-rc.1 final production release-candidate gates passed.")
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--dependency-self-check"]:
        print("PASS: v1.0 RC validator direct-import contract")
        raise SystemExit(0)
    if sys.argv[1:] == ["--source-path-self-check"]:
        result = subprocess.run(
            [sys.executable, "-c", "import sazmanhr; import ci.release_identity; import ci.real_data_bundle"],
            cwd=ROOT, env=source_test_environment({}), text=True, capture_output=True,
        )
        if result.returncode:
            print(result.stdout, end="")
            print(result.stderr, end="", file=sys.stderr)
            fail("clean RC candidate source-path contract failed")
        print("PASS: v1.0 RC validator clean source-path contract")
        raise SystemExit(0)
    raise SystemExit(main())
