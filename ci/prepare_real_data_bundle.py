#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ci.real_data_bundle import BundleError, create_encrypted_bundle  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare the protected HRM v0.6 real-data CI bundle.")
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--bundle", type=Path, default=ROOT / "ci" / "real-data" / "hrm-real-data-v060b1.enc")
    parser.add_argument("--key-file", type=Path, default=ROOT / "private-data" / "hrm-v060b1-fernet.key")
    args = parser.parse_args()
    try:
        result = create_encrypted_bundle(args.input_dir, args.bundle, args.key_file)
    except BundleError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("PASS: encrypted real-data bundle prepared; plaintext workbooks were not copied into Git.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
