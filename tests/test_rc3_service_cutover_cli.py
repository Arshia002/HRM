from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import sazmanhr.server as server


class Rc3ServiceCutoverCliTests(unittest.TestCase):
    def test_prepare_cutover_cli_requires_state_file_and_dispatches_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state_path = root / "service-cutover-state.json"
            target = root / "runtime" / "HRMService.exe"
            target.parent.mkdir()
            target.write_bytes(b"service")

            with mock.patch.object(
                server,
                "create_windows_service_cutover_journal",
                create=True,
                return_value={"phase": "snapshotted", "committed": False},
            ) as prepare:
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    code = server.main(
                        [
                            "--data-dir",
                            str(root),
                            "--prepare-service-cutover",
                            "HRMCentralService",
                            "--service-cutover-state-file",
                            str(state_path),
                            "--service-image-executable",
                            str(target),
                        ]
                    )

            self.assertEqual(code, 0)
            prepare.assert_called_once_with(
                state_path.resolve(),
                "HRMCentralService",
                target.resolve(),
            )
            self.assertIn('"phase": "snapshotted"', stdout.getvalue())

    def test_advance_cutover_cli_dispatches_exact_phase(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state_path = root / "service-cutover-state.json"

            with mock.patch.object(
                server,
                "advance_service_cutover_journal",
                create=True,
                return_value={"phase": "image_switched", "committed": False},
            ) as advance:
                code = server.main(
                    [
                        "--data-dir",
                        str(root),
                        "--advance-service-cutover",
                        "image_switched",
                        "--service-cutover-state-file",
                        str(state_path),
                    ]
                )

            self.assertEqual(code, 0)
            advance.assert_called_once_with(
                state_path.resolve(),
                "image_switched",
            )

    def test_commit_cutover_cli_dispatches_durable_commit(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state_path = root / "service-cutover-state.json"

            with mock.patch.object(
                server,
                "mark_service_cutover_committed",
                create=True,
                return_value={"phase": "committed", "committed": True},
            ) as commit:
                code = server.main(
                    [
                        "--data-dir",
                        str(root),
                        "--commit-service-cutover",
                        "--service-cutover-state-file",
                        str(state_path),
                    ]
                )

            self.assertEqual(code, 0)
            commit.assert_called_once_with(state_path.resolve())

    def test_cutover_cli_rejects_multiple_journal_actions(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state_path = root / "service-cutover-state.json"

            code = server.main(
                [
                    "--data-dir",
                    str(root),
                    "--advance-service-cutover",
                    "service_stopped",
                    "--commit-service-cutover",
                    "--service-cutover-state-file",
                    str(state_path),
                ]
            )
            self.assertEqual(code, 1)

    def test_cutover_cli_requires_state_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            code = server.main(
                [
                    "--data-dir",
                    str(root),
                    "--commit-service-cutover",
                ]
            )
            self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
