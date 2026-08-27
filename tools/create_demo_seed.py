#!/usr/bin/env python3
"""Create the synthetic seed used by tests and unsigned public builds."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from sazmanhr.demo_data import create_demo_seed  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a synthetic HRM seed database.")
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT / "data" / "seed" / "hrm-seed.sqlite",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    manifest = create_demo_seed(args.output, overwrite=args.force)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
