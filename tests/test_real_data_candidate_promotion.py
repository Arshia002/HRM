import contextlib
import hashlib
import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.real_data_migration import production


ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "data" / "seed" / "sazmanhr-seed.sqlite"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _set_metadata(path: Path, **values: str | None) -> None:
    with contextlib.closing(sqlite3.connect(path)) as conn:
        for key, value in values.items():
            if value is None:
                conn.execute("DELETE FROM metadata WHERE key=?", (key,))
            else:
                conn.execute(
                    "INSERT OR REPLACE INTO metadata(key,value) VALUES(?,?)",
                    (key, value),
                )
        conn.commit()


def _metadata(path: Path, key: str) -> str | None:
    with contextlib.closing(sqlite3.connect(path)) as conn:
        row = conn.execute(
            "SELECT value FROM metadata WHERE key=?",
            (key,),
        ).fetchone()
    return None if row is None else str(row[0])


def _personnel_count(path: Path) -> int:
    with contextlib.closing(sqlite3.connect(path)) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM personnel").fetchone()[0])


class InitialRealDataCandidatePromotionTests(unittest.TestCase):
    def _make_live_and_candidate(self, root: Path) -> tuple[Path, Path, Path]:
        live = root / "live" / "hrm.sqlite"
        candidate = root / "candidate" / "hrm.sqlite"
        backups = root / "backups"
        live.parent.mkdir(parents=True)
        candidate.parent.mkdir(parents=True)
        shutil.copy2(SEED, live)
        shutil.copy2(SEED, candidate)

        _set_metadata(
            live,
            acceptance_marker="live-before-promotion",
        )
        _set_metadata(
            candidate,
            dataset_kind="protected-real-data-candidate",
            seed_mode=None,
            dataset_personnel_count=str(_personnel_count(candidate)),
            acceptance_marker="candidate-to-promote",
        )
        return live, candidate, backups

    def test_success_creates_verified_backup_and_atomically_promotes_candidate(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            live, candidate, backups = self._make_live_and_candidate(root)
            expected_personnel = _personnel_count(candidate)
            candidate_before = _sha256(candidate)

            result = production.promote_initial_enterprise_candidate(
                candidate,
                live,
                backups,
                expected_personnel=expected_personnel,
            )

            self.assertEqual(_sha256(candidate), candidate_before)
            self.assertEqual(_sha256(live), candidate_before)
            self.assertEqual(_metadata(live, "acceptance_marker"), "candidate-to-promote")

            backup = backups / str(result["backup_file"])
            self.assertTrue(backup.is_file())
            self.assertEqual(_sha256(backup), str(result["backup_sha256"]))
            self.assertEqual(_metadata(backup, "acceptance_marker"), "live-before-promotion")
            self.assertEqual(str(result["promoted_sha256"]), candidate_before)

            ok, detail = production.sqlite_integrity(live)
            self.assertTrue(ok, detail)
            with contextlib.closing(sqlite3.connect(live)) as conn:
                self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_wrong_candidate_count_is_rejected_before_backup_or_live_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            live, candidate, backups = self._make_live_and_candidate(root)
            live_before = _sha256(live)

            with self.assertRaisesRegex(ValueError, "Personnel count mismatch"):
                production.promote_initial_enterprise_candidate(
                    candidate,
                    live,
                    backups,
                    expected_personnel=_personnel_count(candidate) + 1,
                )

            self.assertEqual(_sha256(live), live_before)
            self.assertEqual(_metadata(live, "acceptance_marker"), "live-before-promotion")
            self.assertFalse(backups.exists())

    def test_failure_after_replace_restores_verified_live_backup(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            live, candidate, backups = self._make_live_and_candidate(root)
            expected_personnel = _personnel_count(candidate)
            candidate_before = _sha256(candidate)
            real_replace = production.replace_with_retry
            calls = 0

            def replace_then_fail_once(source: Path, destination: Path) -> None:
                nonlocal calls
                calls += 1
                if calls == 1:
                    os.replace(source, destination)
                    raise RuntimeError("injected failure after live replacement")
                real_replace(source, destination)

            with mock.patch.object(
                production,
                "replace_with_retry",
                side_effect=replace_then_fail_once,
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "injected failure after live replacement",
                ):
                    production.promote_initial_enterprise_candidate(
                        candidate,
                        live,
                        backups,
                        expected_personnel=expected_personnel,
                    )

            self.assertGreaterEqual(calls, 2)
            self.assertEqual(_metadata(live, "acceptance_marker"), "live-before-promotion")
            self.assertEqual(_sha256(candidate), candidate_before)
            ok, detail = production.sqlite_integrity(live)
            self.assertTrue(ok, detail)


if __name__ == "__main__":
    unittest.main()
