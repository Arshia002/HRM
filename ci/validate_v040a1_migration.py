from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_NAMES = {
    "اکسل رسمی.xls",
    "اکسل شرکتی - حجمی - پیمانکاری.xls",
    "اکسل پست با نام.xlsx",
    "شهرستان.xls",
}


def fail(message: str) -> None:
    print("FAIL:", message)
    raise SystemExit(1)


def main() -> int:
    required = [
        ROOT / "tools/real_data_migration/cli.py",
        ROOT / "tools/real_data_migration/reconcile.py",
        ROOT / "tests/test_v040a1_migration.py",
        ROOT / "docs/V040A1-REAL-DATA-MIGRATION.md",
        ROOT / "VERSION-V040A1.json",
    ]
    for path in required:
        if not path.exists():
            fail(f"missing {path.relative_to(ROOT)}")

    bad: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if path.name in FORBIDDEN_NAMES:
            bad.append(str(path.relative_to(ROOT)))
        if "migration/input" in path.as_posix() and path.suffix.lower() in {".xls", ".xlsx", ".csv"}:
            bad.append(str(path.relative_to(ROOT)))
    if bad:
        fail("real/private input data found in package: " + ", ".join(sorted(set(bad))))

    meta = json.loads((ROOT / "VERSION-V040A1.json").read_text(encoding="utf-8"))
    if meta.get("version") != "0.4.0-alpha.1":
        fail("wrong version metadata")

    result = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_v040a1_migration.py", "-v"],
        cwd=ROOT,
    )
    if result.returncode:
        return result.returncode

    print("PASS: HRM v0.4.0-alpha.1 migration gates passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
