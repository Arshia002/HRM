from __future__ import annotations

import importlib.util
import shutil
import unittest
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = ROOT / "ci" / "validate_package_contract.py"
PUBLIC_TEMPLATE = ROOT / "web" / "assets" / "templates" / "SazmanHR-Monthly-Import-Template.xlsx"


def _load_validator():
    spec = importlib.util.spec_from_file_location("hrm_package_validator", VALIDATOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load package validator: {VALIDATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PublicSafeRuntimeTemplateContractTests(unittest.TestCase):
    def test_hash_identical_runtime_copy_allowed_but_corruption_rejected(self) -> None:
        validator = _load_validator()
        probe_root = ROOT / "build-output" / f"validator-contract-{uuid.uuid4().hex}"
        probe = probe_root / "web" / "assets" / "templates" / PUBLIC_TEMPLATE.name
        probe.parent.mkdir(parents=True, exist_ok=False)
        try:
            shutil.copy2(PUBLIC_TEMPLATE, probe)
            validator.validate_public_safe_seed()

            with probe.open("ab") as handle:
                handle.write(b"\nHRM_VALIDATOR_CORRUPTION_PROBE\n")

            with self.assertRaisesRegex(
                RuntimeError,
                r"Public CI package contains forbidden data file",
            ):
                validator.validate_public_safe_seed()
        finally:
            shutil.rmtree(probe_root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
