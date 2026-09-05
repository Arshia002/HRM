#!/usr/bin/env python3
"""Delete only known obsolete tracked evidence before the v1.0 RC commit."""
from __future__ import annotations
import argparse
from pathlib import Path

OBSOLETE = (
    "#Uf02a.iss",
    "test-evidence/ci-local-unit-tests.log",
    "test-evidence/linux-unit-tests.log",
    "test-evidence/unicode-repo-regression-tests.log",
    "test-evidence/compile-check.log",
    "test-evidence/unicode-repo-regression-contract.log",
    "test-evidence/yaml-json-check.log",
    "test-evidence/unit-tests.log",
    "test-evidence/contract-validation.log",
)

def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]); args=parser.parse_args()
    root=args.root.resolve(); removed=[]
    for relative in OBSOLETE:
        target=root/relative
        if target.is_file():
            target.unlink(); removed.append(relative)
    print(f"PASS: final-candidate repository hygiene removed {len(removed)} obsolete tracked artifact(s).")
    return 0
if __name__=='__main__': raise SystemExit(main())
