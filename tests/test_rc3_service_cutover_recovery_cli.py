from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import sazmanhr.server as server


class Rc3ServiceCutoverRecoveryCliTests(unittest.TestCase):
    def test_recover_cutover_cli_dispatches_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state_path = root / "service-cutover-state.json"

            with mock.patch.object(
                server,
                "recover_windows_service_cutover",
                create=True,
                return_value={"phase": "recovered", "committed": False},
            ) as recover:
                code = server.main(
                    [
                        "--data-dir",
                        str(root),
                        "--recover-service-cutover",
                        "--service-cutover-state-file",
                        str(state_path),
                    ]
                )

            self.assertEqual(code, 0)
            recover.assert_called_once_with(state_path.resolve())

    def test_recover_cutover_cli_requires_state_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            code = server.main(
                [
                    "--data-dir",
                    str(root),
                    "--recover-service-cutover",
                ]
            )

            self.assertEqual(code, 1)

    def test_recover_cutover_cli_is_mutually_exclusive_with_commit(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state_path = root / "service-cutover-state.json"

            code = server.main(
                [
                    "--data-dir",
                    str(root),
                    "--recover-service-cutover",
                    "--commit-service-cutover",
                    "--service-cutover-state-file",
                    str(state_path),
                ]
            )

            self.assertEqual(code, 1)

    def test_recover_cutover_cli_is_mutually_exclusive_with_advance(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state_path = root / "service-cutover-state.json"

            code = server.main(
                [
                    "--data-dir",
                    str(root),
                    "--recover-service-cutover",
                    "--advance-service-cutover",
                    "service_stopped",
                    "--service-cutover-state-file",
                    str(state_path),
                ]
            )

            self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
