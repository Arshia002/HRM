from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from sazmanhr.legacy_upgrade import (
    commit_legacy_database_upgrade,
    restore_legacy_database_upgrade,
)


class CurrentDatabaseUpgradeCommitTests(unittest.TestCase):
    def test_current_noop_upgrade_state_can_be_durably_committed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            database = root / "hrm.sqlite"
            database.write_bytes(b"current-database")
            state_path = root / "installer-upgrade-state.json"
            state_path.write_text(
                json.dumps(
                    {
                        "schema": 1,
                        "performed": False,
                        "status": "current",
                        "database": str(database.resolve()),
                    },
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )

            result = commit_legacy_database_upgrade(state_path)

            self.assertTrue(result["ok"])
            self.assertTrue(result["committed"])
            persisted = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertTrue(persisted["committed"])
            self.assertFalse(persisted["performed"])
            self.assertEqual(persisted["status"], "current")

    def test_restore_after_committed_current_state_is_noop(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            database = root / "hrm.sqlite"
            database.write_bytes(b"current-database")
            before = database.read_bytes()
            state_path = root / "installer-upgrade-state.json"
            state_path.write_text(
                json.dumps(
                    {
                        "schema": 1,
                        "performed": False,
                        "status": "current",
                        "database": str(database.resolve()),
                    },
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )

            commit_legacy_database_upgrade(state_path)
            result = restore_legacy_database_upgrade(state_path)

            self.assertTrue(result["ok"])
            self.assertFalse(result["restored"])
            self.assertEqual(result["reason"], "transaction_committed")
            self.assertEqual(database.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
