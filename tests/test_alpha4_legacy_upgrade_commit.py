from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from sazmanhr.legacy_upgrade import (
    LegacyUpgradeError,
    commit_legacy_database_upgrade,
    restore_legacy_database_upgrade,
)


class Alpha4LegacyUpgradeCommitTests(unittest.TestCase):
    def _write_upgraded_state(self, root: Path) -> tuple[Path, Path, Path, dict[str, object]]:
        database = root / "hrm.sqlite"
        backup = root / "pre-alpha4-upgrade.sqlite"
        state_path = root / "installer-upgrade-state.json"

        database.write_bytes(b"new-database-bytes")
        backup.write_bytes(b"old-database-bytes")
        backup_sha256 = hashlib.sha256(backup.read_bytes()).hexdigest()

        state: dict[str, object] = {
            "schema": 1,
            "performed": True,
            "status": "upgraded",
            "database": str(database.resolve()),
            "backup": str(backup.resolve()),
            "backup_sha256": backup_sha256,
            "critical_counts": {
                "personnel": 12,
                "org_units": 7,
            },
            "source": {
                "product_id": "hrm-kepdco",
                "schema_generation": "1",
                "schema_version": "5",
            },
            "target": {
                "product_id": "sazmanhr-enterprise",
                "schema_generation": "16",
                "schema_version": "9",
            },
        }
        state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return state_path, database, backup, state

    def test_commit_marks_upgraded_transaction_durably(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state_path, _database, _backup, _before = self._write_upgraded_state(root)

            result = commit_legacy_database_upgrade(state_path)

            self.assertTrue(result["ok"])
            self.assertTrue(result["committed"])
            persisted = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertTrue(persisted["committed"])
            self.assertEqual(persisted["status"], "upgraded")
            self.assertFalse(state_path.with_suffix(state_path.suffix + ".staged").exists())

    def test_commit_preserves_rollback_snapshot_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state_path, _database, _backup, before = self._write_upgraded_state(root)

            commit_legacy_database_upgrade(state_path)
            after = json.loads(state_path.read_text(encoding="utf-8"))

            for key in (
                "database",
                "backup",
                "backup_sha256",
                "critical_counts",
                "source",
                "target",
            ):
                self.assertEqual(after[key], before[key])

    def test_restore_after_commit_is_noop_and_leaves_database_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state_path, database, _backup, _before = self._write_upgraded_state(root)
            original_database_bytes = database.read_bytes()

            commit_legacy_database_upgrade(state_path)
            restored = restore_legacy_database_upgrade(state_path)

            self.assertTrue(restored["ok"])
            self.assertFalse(restored["restored"])
            self.assertEqual(restored["reason"], "transaction_committed")
            self.assertEqual(database.read_bytes(), original_database_bytes)
            persisted = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertTrue(persisted["committed"])
            self.assertEqual(persisted["status"], "upgraded")

    def test_commit_missing_or_invalid_state_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            missing = root / "missing.json"
            with self.assertRaises(LegacyUpgradeError):
                commit_legacy_database_upgrade(missing)

            invalid = root / "invalid.json"
            invalid.write_text("{not-json", encoding="utf-8")
            with self.assertRaises(LegacyUpgradeError):
                commit_legacy_database_upgrade(invalid)

    def test_prepared_transaction_cannot_be_committed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state_path, _database, _backup, state = self._write_upgraded_state(root)
            state["status"] = "prepared"
            state_path.write_text(
                json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(LegacyUpgradeError, "upgraded"):
                commit_legacy_database_upgrade(state_path)

            persisted = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertNotIn("committed", persisted)
            self.assertEqual(persisted["status"], "prepared")


if __name__ == "__main__":
    unittest.main()
