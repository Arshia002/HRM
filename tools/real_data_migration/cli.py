from __future__ import annotations
import argparse
import json
from pathlib import Path
from .engine import load_directory
from .models import Issue
from .production import CONFIRMATION, apply_to_enterprise, validate_target
from .reconcile import reconcile, summary
from .report import write_private_normalized_json, write_reports
from .staging import create_staging_db


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="HRM real-data import dry-run/staging tool")
    p.add_argument("--self-test", action="store_true", help="Verify the frozen migration runtime and exit")
    p.add_argument("--input-dir", type=Path)
    p.add_argument("--output-dir", type=Path)
    p.add_argument("--expected-personnel", type=int)
    p.add_argument("--expected-fixed", type=int)
    p.add_argument("--expected-named", type=int)
    p.add_argument("--stage", action="store_true", help="Create private staging.sqlite only when reconciliation has zero errors")
    p.add_argument("--write-normalized-private", action="store_true", help="Write normalized PII output into private output directory")
    p.add_argument("--target-db", type=Path, help="Read-only Enterprise target validation")
    p.add_argument("--apply-to-db", type=Path, help="Apply to a compatible Enterprise database after backup")
    p.add_argument("--backup-dir", type=Path, help="Required private backup directory for production apply")
    p.add_argument("--confirm-apply", default="", help=f"Required literal confirmation token: {CONFIRMATION}")
    p.add_argument("--expected-chart-fixed", type=int, default=536)
    p.add_argument("--expected-chart-named", type=int, default=32)
    p.add_argument("--expected-chart-total", type=int, default=568)
    p.add_argument("--actor-id", default="")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.self_test:
        import openpyxl  # type: ignore
        import xlrd  # type: ignore
        print(json.dumps({
            "status": "ok", "openpyxl": openpyxl.__version__, "xlrd": xlrd.__version__,
            "confirmation_contract": CONFIRMATION,
        }))
        return 0
    if args.input_dir is None or args.output_dir is None:
        raise SystemExit("--input-dir and --output-dir are required unless --self-test is used.")
    if args.apply_to_db is not None and args.backup_dir is None:
        raise SystemExit("--backup-dir is required with --apply-to-db.")
    if args.apply_to_db is not None and args.target_db is not None and args.apply_to_db.resolve() != args.target_db.resolve():
        raise SystemExit("--target-db and --apply-to-db must identify the same database when both are supplied.")

    ds = reconcile(
        load_directory(args.input_dir), args.expected_fixed, args.expected_named, args.expected_personnel,
    )
    target_db = args.apply_to_db or args.target_db
    target_result = None
    if target_db is not None and not any(issue.severity == "error" for issue in ds.issues):
        try:
            target_result = validate_target(
                ds, target_db,
                expected_personnel=args.expected_personnel or len(ds.persons),
                expected_chart_fixed=args.expected_chart_fixed,
                expected_chart_named=args.expected_chart_named,
                expected_chart_total=args.expected_chart_total,
            )
        except Exception as exc:
            ds.issues.append(Issue("error", "TARGET_PREFLIGHT_FAILED", str(exc)))
    write_reports(ds, args.output_dir)
    if target_result is not None:
        (args.output_dir / "target-preflight.json").write_text(
            json.dumps(target_result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
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
    if args.apply_to_db is not None:
        if not s["eligible_for_staging"]:
            print("REFUSED: production apply is blocked until reconciliation and target errors are resolved.")
            return 2
        result = apply_to_enterprise(
            ds, args.apply_to_db, args.backup_dir,
            confirmation=args.confirm_apply,
            expected_personnel=args.expected_personnel or len(ds.persons),
            expected_chart_fixed=args.expected_chart_fixed,
            expected_chart_named=args.expected_chart_named,
            expected_chart_total=args.expected_chart_total,
            actor_id=args.actor_id or None,
        )
        (args.output_dir / "production-apply-summary.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps({
            "status": "applied", "updated_personnel": result["updated_personnel"],
            "named_position_assignments": result["named_position_assignments"],
            "backup_file": result["backup_file"],
        }, ensure_ascii=False))
    return 0 if s["errors"] == 0 else 1

if __name__ == "__main__":
    raise SystemExit(main())
