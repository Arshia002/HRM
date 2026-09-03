#!/usr/bin/env python3
"""Isolated RC hardening runner with an explicit source import boundary."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARDENING_MODULES = (
    "tests.test_rc_release_identity",
    "tests.test_rc_network_resilience",
    "tests.test_rc_disaster_recovery",
    "tests.test_rc_diagnostics_privacy",
)


def source_test_environment(base: dict[str, str] | None = None) -> dict[str, str]:
    environment = dict(os.environ if base is None else base)
    paths = [str(ROOT), str(ROOT / "src")]
    inherited = environment.get("PYTHONPATH", "")
    if inherited:
        paths.append(inherited)
    environment["PYTHONPATH"] = os.pathsep.join(paths)
    return environment


def source_path_self_check() -> int:
    result = subprocess.run(
        [sys.executable, "-c", "import sazmanhr; import ci.release_identity; import tests.test_rc_network_resilience; import tests.test_rc_disaster_recovery"],
        cwd=ROOT,
        env=source_test_environment({}),
        text=True,
        capture_output=True,
    )
    if result.returncode:
        print(result.stdout, end="")
        print(result.stderr, end="", file=sys.stderr)
        print("FAIL: RC hardening clean source-path contract")
        return result.returncode
    print("PASS: RC hardening clean source-path contract")
    return 0


def main() -> int:
    result = subprocess.run(
        [sys.executable, "-m", "unittest", *HARDENING_MODULES, "-v"],
        cwd=ROOT,
        env=source_test_environment(),
    )
    if result.returncode:
        return result.returncode
    print("PASS: isolated RC network, disaster-recovery and diagnostics hardening gates passed.")
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--source-path-self-check"]:
        raise SystemExit(source_path_self_check())
    if sys.argv[1:]:
        raise SystemExit("Usage: validate_rc_hardening.py [--source-path-self-check]")
    raise SystemExit(main())
