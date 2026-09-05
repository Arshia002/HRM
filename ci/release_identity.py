#!/usr/bin/env python3
"""Single release-identity contract for the current HRM production-history RC overlay."""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
METADATA_FILE = ROOT / "VERSION-V080RC1.json"


@dataclass(frozen=True)
class ReleaseIdentity:
    version: str
    package_revision: str
    baseline_tag: str
    baseline_commit: str
    branch: str
    tested_artifact: str
    failure_artifact: str
    metadata: dict[str, object]


def load_identity() -> ReleaseIdentity:
    metadata = json.loads(METADATA_FILE.read_text(encoding="utf-8"))
    version = str(metadata.get("version", "")).strip()
    package_revision = str(metadata.get("package_revision", "")).strip()
    branch = str(metadata.get("pilot_branch", "")).strip()
    baseline_tag = str(metadata.get("baseline_tag", "")).strip()
    baseline_commit = str(metadata.get("baseline_commit", "")).strip()
    if not all((version, package_revision, branch, baseline_tag, baseline_commit)):
        raise RuntimeError("RC release identity metadata is incomplete.")
    if (ROOT / "VERSION").read_text(encoding="utf-8").strip() != version:
        raise RuntimeError("VERSION does not match VERSION-V080RC1.json")
    if (ROOT / "CI-PACKAGE-VERSION").read_text(encoding="utf-8").strip() != package_revision:
        raise RuntimeError("CI-PACKAGE-VERSION does not match VERSION-V080RC1.json")
    return ReleaseIdentity(
        version=version,
        package_revision=package_revision,
        baseline_tag=baseline_tag,
        baseline_commit=baseline_commit,
        branch=branch,
        tested_artifact=f"HRM-{version}-Tested-Setup",
        failure_artifact=f"HRM-{version}-Failure-Logs",
        metadata=metadata,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--print", dest="field", choices=(
        "version", "package_revision", "branch", "baseline_tag", "baseline_commit",
        "tested_artifact", "failure_artifact",
    ))
    args = parser.parse_args()
    identity = load_identity()
    if args.field:
        print(getattr(identity, args.field))
    else:
        print(json.dumps({
            "version": identity.version,
            "package_revision": identity.package_revision,
            "branch": identity.branch,
            "baseline_tag": identity.baseline_tag,
            "baseline_commit": identity.baseline_commit,
            "tested_artifact": identity.tested_artifact,
            "failure_artifact": identity.failure_artifact,
        }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
