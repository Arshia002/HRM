from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import sazmanhr.server as server


class Rc3FreshInstallTransactionCliTests(unittest.TestCase):
    def _args(self, root: Path) -> tuple[Path, Path]:
        state = root / "service-cutover-state.json"
        target = root / "ServiceRuntime" / "svc-new" / "HRMService.exe"
        return state, target

    def test_prepare_service_install_dispatches_fresh_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state, target = self._args(root)

            with mock.patch.object(
                server,
                "create_windows_service_install_journal",
                create=True,
                return_value={
                    "service_name": "HRMCentralService",
                    "service_existed_before": False,
                    "phase": "snapshotted",
                    "committed": False,
                },
            ) as prepare:
                code = server.main(
                    [
                        "--data-dir",
                        str(root),
                        "--prepare-service-install",
                        "HRMCentralService",
                        "--service-image-executable",
                        str(target),
                        "--service-cutover-state-file",
                        str(state),
                    ]
                )

            self.assertEqual(code, 0)
            prepare.assert_called_once()
            args = prepare.call_args.args
            self.assertEqual(args[0], state.resolve())
            self.assertEqual(args[1], "HRMCentralService")
            self.assertEqual(Path(args[2]), target.resolve())

    def test_prepare_service_install_requires_state_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, target = self._args(root)

            code = server.main(
                [
                    "--data-dir",
                    str(root),
                    "--prepare-service-install",
                    "HRMCentralService",
                    "--service-image-executable",
                    str(target),
                ]
            )

            self.assertEqual(code, 1)

    def test_prepare_service_install_requires_target_executable(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state, _ = self._args(root)

            code = server.main(
                [
                    "--data-dir",
                    str(root),
                    "--prepare-service-install",
                    "HRMCentralService",
                    "--service-cutover-state-file",
                    str(state),
                ]
            )

            self.assertEqual(code, 1)

    def test_prepare_service_install_is_mutually_exclusive_with_cutover_prepare(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state, target = self._args(root)

            code = server.main(
                [
                    "--data-dir",
                    str(root),
                    "--prepare-service-install",
                    "HRMCentralService",
                    "--prepare-service-cutover",
                    "HRMCentralService",
                    "--service-image-executable",
                    str(target),
                    "--service-cutover-state-file",
                    str(state),
                ]
            )

            self.assertEqual(code, 1)

    def test_installer_coordinator_rejects_fresh_prepare_low_level_action(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state, target = self._args(root)
            database_state = root / "installer-upgrade-state.json"

            code = server.main(
                [
                    "--data-dir",
                    str(root),
                    "--recover-installer-upgrade",
                    "--prepare-service-install",
                    "HRMCentralService",
                    "--service-image-executable",
                    str(target),
                    "--service-cutover-state-file",
                    str(state),
                    "--database-upgrade-state-file",
                    str(database_state),
                ]
            )

            self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
