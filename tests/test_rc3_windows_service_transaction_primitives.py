from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from sazmanhr.server import verify_service_runtime
from sazmanhr.windows_service_control import (
    SERVICE_STOPPED,
    delete_windows_service,
    set_windows_service_binary_path,
)


def _make_manifest(runtime: Path) -> dict[str, object]:
    entries: list[dict[str, object]] = []
    tree = hashlib.sha256()
    files = sorted(
        (item.relative_to(runtime).as_posix(), item)
        for item in runtime.rglob("*")
        if item.is_file()
    )
    for relative, path in files:
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        size = len(raw)
        entries.append({"path": relative, "bytes": size, "sha256": digest})
        tree.update(relative.encode("utf-8"))
        tree.update(b"\0")
        tree.update(str(size).encode("ascii"))
        tree.update(b"\0")
        tree.update(bytes.fromhex(digest))
    exe_hash = next(str(item["sha256"]) for item in entries if item["path"] == "HRMService.exe")
    return {
        "schema": 1,
        "tree_sha256": tree.hexdigest(),
        "service_executable_sha256": exe_hash,
        "files": entries,
    }


class Rc3WindowsServiceTransactionPrimitiveTests(unittest.TestCase):
    def test_builder_uses_platform_independent_posix_manifest_order(self) -> None:
        builder = (
            Path(__file__).resolve().parents[1]
            / "build"
            / "windows"
            / "build_windows.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "(path.relative_to(runtime_dir).as_posix(), path)",
            builder,
        )
        self.assertIn("for relative, path in files:", builder)
        self.assertNotIn(
            'files = sorted(path for path in runtime_dir.rglob("*") if path.is_file())',
            builder,
        )

    def test_runtime_manifest_accepts_exact_tree_and_rejects_corruption(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            runtime = Path(temp)
            (runtime / "_internal").mkdir()
            (runtime / "HRMService.exe").write_bytes(b"service")
            (runtime / "_internal" / "python311.dll").write_bytes(b"python")
            manifest = _make_manifest(runtime)
            (runtime / "runtime-manifest.json").write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            result = verify_service_runtime(runtime)
            self.assertTrue(result["ok"])
            self.assertEqual(result["files"], 2)
            (runtime / "_internal" / "python311.dll").write_bytes(b"corrupt")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                verify_service_runtime(runtime)

    def test_image_path_switch_quotes_and_verifies_without_shell(self) -> None:
        store = {"value": r'"C:\Program Files\HRM\old.exe"'}

        def reader(name: str) -> str | None:
            self.assertEqual(name, "HRMCentralService")
            return store["value"]

        def changer(name: str, image_path: str) -> None:
            self.assertEqual(name, "HRMCentralService")
            store["value"] = image_path

        target = r"C:\Program Files\HRM\ServiceRuntime\svc-test\HRMService.exe"
        result = set_windows_service_binary_path(
            "HRMCentralService", target, reader=reader, changer=changer
        )
        self.assertEqual(store["value"], f'"{target}"')
        self.assertEqual(result["executable"], target)

    def test_image_path_switch_fails_closed_if_verification_does_not_change(self) -> None:
        old = r'"C:\Program Files\HRM\old.exe"'
        with self.assertRaisesRegex(RuntimeError, "verification failed"):
            set_windows_service_binary_path(
                "HRMCentralService",
                r"C:\Program Files\HRM\new.exe",
                reader=lambda _name: old,
                changer=lambda _name, _path: None,
            )

    def test_delete_service_requires_stopped_state(self) -> None:
        calls: list[tuple[str, str]] = []

        def runner(action: str, name: str) -> tuple[int, str]:
            calls.append((action, name))
            if action == "queryex":
                return 0, f"STATE              : {SERVICE_STOPPED}  STOPPED\n"
            if action == "delete":
                return 0, "DELETE_PENDING"
            raise AssertionError(action)

        result = delete_windows_service("HRMCentralService", runner=runner)
        self.assertTrue(result["deleted"])
        self.assertEqual(calls[-1], ("delete", "HRMCentralService"))


if __name__ == "__main__":
    unittest.main()
