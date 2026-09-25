import contextlib
import hashlib
import sqlite3
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from tools.real_data_migration import production


ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "data" / "seed" / "sazmanhr-seed.sqlite"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _person(number: str, position_no: str):
    return types.SimpleNamespace(
        personnel_no=number,
        first_name="Test",
        last_name=number,
        national_id="",
        employment_type="employee",
        org_unit="Acceptance Unit",
        location="Acceptance Site",
        position_no=position_no,
        position_title=f"Position {position_no}",
    )


def _position(position_no: str, occupant: str):
    return types.SimpleNamespace(
        position_no=position_no,
        title=f"Position {position_no}",
        org_unit="Acceptance Unit",
        location="Acceptance Site",
        position_type="fixed",
        occupant_personnel_no=occupant,
    )


def _dataset(count: int):
    people = [_person(f"P{i:04d}", f"POS{i:04d}") for i in range(1, count + 1)]
    positions = [_position(p.position_no, p.personnel_no) for p in people]
    return types.SimpleNamespace(
        persons=people,
        positions=positions,
        issues=[],
        source_files=["acceptance-fixture.xlsx"],
    )


class InitialRealDataProvisioningTests(unittest.TestCase):
    """Contract for the missing fresh-install -> real-data provisioning phase.

    These tests intentionally describe a new production primitive.  The current
    RC3 source is expected to fail until build_initial_enterprise_candidate()
    exists and implements the contract below.
    """

    def test_bootstrap_replaces_synthetic_personnel_set_before_production_apply(self):
        dataset = _dataset(2)
        seed_before = _sha256(SEED)

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            candidate = root / "candidate.sqlite"
            candidate_backups = root / "candidate-backups"

            def inspect_prepared_target(ds, database_path, backup_dir, **kwargs):
                self.assertIs(ds, dataset)
                self.assertEqual(Path(database_path).resolve(), candidate.resolve())
                self.assertEqual(Path(backup_dir).resolve(), candidate_backups.resolve())
                with contextlib.closing(sqlite3.connect(candidate)) as conn:
                    actual = {
                        str(row[0])
                        for row in conn.execute(
                            "SELECT personnel_no FROM personnel ORDER BY personnel_no"
                        )
                    }
                    self.assertEqual(actual, {"P0001", "P0002"})
                    self.assertEqual(
                        conn.execute("PRAGMA integrity_check").fetchone()[0], "ok"
                    )
                    self.assertEqual(
                        len(conn.execute("PRAGMA foreign_key_check").fetchall()), 0
                    )
                    metadata = dict(
                        conn.execute(
                            "SELECT key,value FROM metadata "
                            "WHERE key IN ('dataset_kind','seed_mode')"
                        )
                    )
                    self.assertNotEqual(metadata.get("dataset_kind"), "synthetic-demo")
                    self.assertNotEqual(metadata.get("seed_mode"), "synthetic-demo")
                return {
                    "updated_personnel": 2,
                    "named_position_assignments": 2,
                    "backup_file": "candidate-pre-apply.sqlite",
                    "backup_sha256": "fixture",
                }

            with mock.patch.object(
                production, "apply_to_enterprise", side_effect=inspect_prepared_target
            ) as apply_mock:
                result = production.build_initial_enterprise_candidate(
                    dataset,
                    SEED,
                    candidate,
                    candidate_backups,
                    confirmation=production.CONFIRMATION,
                    expected_personnel=2,
                )

            self.assertEqual(result["updated_personnel"], 2)
            self.assertTrue(candidate.is_file())
            self.assertEqual(apply_mock.call_count, 1)

        self.assertEqual(_sha256(SEED), seed_before)

    def test_bootstrap_rejects_wrong_source_count_without_creating_candidate(self):
        dataset = _dataset(1)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            candidate = root / "candidate.sqlite"
            with self.assertRaisesRegex(ValueError, "Personnel count mismatch"):
                production.build_initial_enterprise_candidate(
                    dataset,
                    SEED,
                    candidate,
                    root / "backups",
                    confirmation=production.CONFIRMATION,
                    expected_personnel=2,
                )
            self.assertFalse(candidate.exists())

    def test_bootstrap_removes_partial_candidate_when_apply_fails(self):
        dataset = _dataset(2)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            candidate = root / "candidate.sqlite"
            with mock.patch.object(
                production, "apply_to_enterprise", side_effect=RuntimeError("injected apply failure")
            ):
                with self.assertRaisesRegex(RuntimeError, "injected apply failure"):
                    production.build_initial_enterprise_candidate(
                        dataset,
                        SEED,
                        candidate,
                        root / "backups",
                        confirmation=production.CONFIRMATION,
                        expected_personnel=2,
                    )
            self.assertFalse(candidate.exists())


if __name__ == "__main__":
    unittest.main()
