from __future__ import annotations
import argparse
import json
from pathlib import Path
from .engine import load_directory
from .reconcile import reconcile, summary
from .report import write_private_normalized_json, write_reports
from .staging import create_staging_db


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="HRM real-data import dry-run/staging tool")
    p.add_argument("--input-dir", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--expected-fixed", type=int)
    p.add_argument("--expected-named", type=int)
    p.add_argument("--stage", action="store_true", help="Create private staging.sqlite only when reconciliation has zero errors")
    p.add_argument("--write-normalized-private", action="store_true", help="Write normalized PII output into private output directory")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    ds = reconcile(load_directory(args.input_dir), args.expected_fixed, args.expected_named)
    write_reports(ds, args.output_dir)
    if args.write_normalized_private:
        write_private_normalized_json(ds, args.output_dir)
    s = summary(ds)
    print(json.dumps(s, ensure_ascii=False))
    if args.stage:
        if not s["eligible_for_staging"]:
            print("REFUSED: staging is blocked until reconciliation errors are resolved.")
            return 2
        create_staging_db(ds, args.output_dir / "staging.sqlite")
        print("PASS: private staging database created.")
    return 0 if s["errors"] == 0 else 1

if __name__ == "__main__":
    raise SystemExit(main())
