from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import sazmanhr.server as server


class Rc3InstallerUpgradeTransactionCliTests(unittest.TestCase):
    def test_recover_installer_upgrade_dispatches_coordinator(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            service_state = root / "service-cutover-state.json"
            database_state = root / "installer-upgrade-state.json"

            with mock.patch.object(
                server,
                "recover_upgrade_transaction",
                create=True,
                return_value={
                    "ok": True,
                    "decision": "rollback",
                    "database_recovered": True,
                    "service_recovered": True,
                },
            ) as recover:
                code = server.main(
                    [
                        "--data-dir",
                        str(root),
                        "--recover-installer-upgrade",
                        "--service-cutover-state-file",
                        str(service_state),
                        "--database-upgrade-state-file",
                        str(database_state),
                    ]
                )

            self.assertEqual(code, 0)
            recover.assert_called_once_with(
                service_state.resolve(),
                database_state.resolve(),
            )

    def test_commit_installer_upgrade_dispatches_coordinator(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            service_state = root / "service-cutover-state.json"
            database_state = root / "installer-upgrade-state.json"

            with mock.patch.object(
                server,
                "commit_upgrade_transaction",
                create=True,
                return_value={
                    "ok": True,
                    "decision": "commit",
                    "service_committed": True,
                    "database_committed": True,
                },
            ) as commit:
                code = server.main(
                    [
                        "--data-dir",
                        str(root),
                        "--commit-installer-upgrade",
                        "--service-cutover-state-file",
                        str(service_state),
                        "--database-upgrade-state-file",
                        str(database_state),
                    ]
                )

            self.assertEqual(code, 0)
            commit.assert_called_once_with(
                service_state.resolve(),
                database_state.resolve(),
            )

    def test_installer_upgrade_action_requires_service_state_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            database_state = root / "installer-upgrade-state.json"

            code = server.main(
                [
                    "--data-dir",
                    str(root),
                    "--recover-installer-upgrade",
                    "--database-upgrade-state-file",
                    str(database_state),
                ]
            )

            self.assertEqual(code, 1)

    def test_installer_upgrade_action_requires_database_state_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            service_state = root / "service-cutover-state.json"

            code = server.main(
                [
                    "--data-dir",
                    str(root),
                    "--recover-installer-upgrade",
                    "--service-cutover-state-file",
                    str(service_state),
                ]
            )

            self.assertEqual(code, 1)

    def test_recover_and_commit_installer_upgrade_are_mutually_exclusive(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            service_state = root / "service-cutover-state.json"
            database_state = root / "installer-upgrade-state.json"

            code = server.main(
                [
                    "--data-dir",
                    str(root),
                    "--recover-installer-upgrade",
                    "--commit-installer-upgrade",
                    "--service-cutover-state-file",
                    str(service_state),
                    "--database-upgrade-state-file",
                    str(database_state),
                ]
            )

            self.assertEqual(code, 1)

    def test_coordinator_action_rejects_low_level_service_action(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            service_state = root / "service-cutover-state.json"
            database_state = root / "installer-upgrade-state.json"

            code = server.main(
                [
                    "--data-dir",
                    str(root),
                    "--recover-installer-upgrade",
                    "--commit-service-cutover",
                    "--service-cutover-state-file",
                    str(service_state),
                    "--database-upgrade-state-file",
                    str(database_state),
                ]
            )

            self.assertEqual(code, 1)

    def test_coordinator_action_rejects_low_level_database_action(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            service_state = root / "service-cutover-state.json"
            database_state = root / "installer-upgrade-state.json"

            code = server.main(
                [
                    "--data-dir",
                    str(root),
                    "--commit-installer-upgrade",
                    "--commit-legacy-database-upgrade",
                    "--service-cutover-state-file",
                    str(service_state),
                    "--database-upgrade-state-file",
                    str(database_state),
                ]
            )

            self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
