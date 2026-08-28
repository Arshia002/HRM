from __future__ import annotations
import csv
import json
from dataclasses import asdict
from pathlib import Path
from .models import Dataset
from .reconcile import summary


def write_reports(ds: Dataset, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "summary": summary(ds),
        "source_files": ds.source_files,
        "issues": [i.to_dict() for i in ds.issues],
    }
    (output_dir / "migration-summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    with (output_dir / "migration-issues.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["severity", "code", "message", "file", "sheet", "row", "entity_ref"])
        for i in ds.issues:
            o = i.origin
            w.writerow([i.severity, i.code, i.message, o.file if o else "", o.sheet if o else "", o.row if o else "", i.entity_ref])


def write_private_normalized_json(ds: Dataset, output_dir: Path) -> None:
    """Write normalized records only into the caller-supplied private output directory."""
    payload = {
        "persons": [asdict(x) for x in ds.persons],
        "positions": [asdict(x) for x in ds.positions],
        "counties": [asdict(x) for x in ds.counties],
    }
    (output_dir / "normalized-private.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
