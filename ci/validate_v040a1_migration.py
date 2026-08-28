from __future__ import annotations
import json, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
FORBIDDEN_NAMES={"اکسل رسمی.xls","اکسل شرکتی - حجمی - پیمانکاری.xls","اکسل پست با نام.xlsx","شهرستان.xls"}

def fail(msg):
    print("FAIL:",msg); raise SystemExit(1)

def main():
    required=[
        ROOT/"tools/real_data_migration/cli.py",
        ROOT/"tools/real_data_migration/reconcile.py",
        ROOT/"tests/test_v040a1_migration.py",
        ROOT/"docs/V040A1-REAL-DATA-MIGRATION.md",
        ROOT/"VERSION-V040A1.json",
    ]
    for p in required:
        if not p.exists(): fail(f"missing {p.relative_to(ROOT)}")
    bad=[]
    for p in ROOT.rglob("*"):
        if not p.is_file(): continue
        if p.name in FORBIDDEN_NAMES: bad.append(str(p.relative_to(ROOT)))
        if "migration/input" in p.as_posix() and p.suffix.lower() in {".xls",".xlsx",".csv"}: bad.append(str(p.relative_to(ROOT)))
    if bad: fail("real/private input data found in package: "+", ".join(bad))
    meta=json.loads((ROOT/"VERSION-V040A1.json").read_text(encoding="utf-8"))
    if meta.get("version")!="0.4.0-alpha.1": fail("wrong version metadata")
    r=subprocess.run([sys.executable,"-m","pytest","-q",str(ROOT/"tests/test_v040a1_migration.py")],cwd=ROOT)
    if r.returncode: raise SystemExit(r.returncode)
    print("PASS: HRM v0.4.0-alpha.1 migration gates passed.")
if __name__=="__main__": main()
