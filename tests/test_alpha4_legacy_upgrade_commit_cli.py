from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import sazmanhr.server as server


class LegacyDatabaseUpgradeCommitCliTests(unittest.TestCase):
    def test_commit_database_upgrade_cli_dispatches_durable_commit(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state_path = root / "installer-upgrade-state.json"

            with mock.patch.object(
                server,
                "commit_legacy_database_upgrade",
                create=True,
                return_value={"ok": True, "committed": True},
            ) as commit:
                code = server.main(
                    [
                        "--data-dir",
                        str(root),
                        "--commit-legacy-database-upgrade",
                        "--database-upgrade-state-file",
                        str(state_path),
                    ]
                )

            self.assertEqual(code, 0)
            commit.assert_called_once()
            actual_state_path = Path(commit.call_args.args[0])
            self.assertEqual(actual_state_path.resolve(), state_path.resolve())

    def test_commit_database_upgrade_cli_requires_state_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            code = server.main(
                [
                    "--data-dir",
                    str(root),
                    "--commit-legacy-database-upgrade",
                ]
            )

            self.assertEqual(code, 1)

    def test_commit_database_upgrade_cli_is_mutually_exclusive_with_upgrade(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state_path = root / "installer-upgrade-state.json"

            code = server.main(
                [
                    "--data-dir",
                    str(root),
                    "--upgrade-legacy-database",
                    "--commit-legacy-database-upgrade",
                    "--database-upgrade-state-file",
                    str(state_path),
                ]
            )

            self.assertEqual(code, 1)

    def test_commit_database_upgrade_cli_is_mutually_exclusive_with_restore(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state_path = root / "installer-upgrade-state.json"

            code = server.main(
                [
                    "--data-dir",
                    str(root),
                    "--restore-legacy-database-upgrade",
                    "--commit-legacy-database-upgrade",
                    "--database-upgrade-state-file",
                    str(state_path),
                ]
            )

            self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
