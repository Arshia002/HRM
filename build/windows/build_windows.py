#!/usr/bin/env python3
"""Native Windows builder for HRM.

This replaces the one-click PowerShell bootstrap so enterprise execution
policies cannot prevent the build before diagnostics are written.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BUILD_ROOT = PROJECT_ROOT / "build-output"
DIST_DIR = BUILD_ROOT / "dist"
WORK_DIR = BUILD_ROOT / "work"
VENV_DIR = BUILD_ROOT / "venv"
INSTALLER = BUILD_ROOT / "installer" / "HRM-Setup-x64.exe"
BUILD_MANIFEST = BUILD_ROOT / "installer" / "build-manifest.json"
DEPENDENCY_SNAPSHOT = BUILD_ROOT / "installer" / "dependencies.txt"
REQUIREMENTS = PROJECT_ROOT / "build" / "windows" / "requirements-build.txt"
INNO_SCRIPT = PROJECT_ROOT / "build" / "windows" / "HRM.iss"
LOG_PATH = BUILD_ROOT / "build.log"


class BuildFailure(RuntimeError):
    pass


def console_safe_text(message: str, encoding: str | None = None) -> str:
    """Return text that can always be written to the active Windows console."""
    target_encoding = encoding or getattr(sys.stdout, "encoding", None) or "ascii"
    try:
        return message.encode(target_encoding, errors="backslashreplace").decode(target_encoding)
    except LookupError:
        return message.encode("ascii", errors="backslashreplace").decode("ascii")


def print_console(message: str = "") -> None:
    print(console_safe_text(message), flush=True)


class BuildLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle = path.open("a", encoding="utf-8", newline="")

    def write(self, message: str = "") -> None:
        line = f"{message}\n"
        self.handle.write(line)
        self.handle.flush()
        print_console(message)

    def close(self) -> None:
        self.handle.close()


def command_text(command: Iterable[object]) -> str:
    return subprocess.list2cmdline([str(item) for item in command])


def run(log: BuildLog, command: list[object], *, env: dict[str, str] | None = None) -> None:
    rendered = command_text(command)
    log.write(f"\n> {rendered}")
    process = subprocess.Popen(
        [str(item) for item in command],
        cwd=PROJECT_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    assert process.stdout is not None
    for line in process.stdout:
        clean = line.rstrip("\r\n")
        log.handle.write(clean + "\n")
        log.handle.flush()
        print_console(clean)
    return_code = process.wait()
    if return_code:
        raise BuildFailure(f"Command failed with exit code {return_code}: {rendered}")


def capture(log: BuildLog, command: list[object], *, env: dict[str, str] | None = None) -> str:
    """Run a command, log its output and return the captured text."""
    rendered = command_text(command)
    log.write(f"\n> {rendered}")
    process = subprocess.run(
        [str(item) for item in command],
        cwd=PROJECT_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    output = process.stdout.rstrip("\r\n")
    if output:
        for line in output.splitlines():
            log.handle.write(line + "\n")
            print_console(line)
        log.handle.flush()
    if process.returncode:
        raise BuildFailure(f"Command failed with exit code {process.returncode}: {rendered}")
    return process.stdout


def sha256(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def read_product_version() -> str:
    """Read and cross-check the human and Python package versions."""
    version = (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-(?:alpha|beta|rc)\.\d+)?", version):
        raise BuildFailure(f"VERSION has an unsupported format: {version!r}")
    package_init = (PROJECT_ROOT / "src" / "sazmanhr" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', package_init, re.MULTILINE)
    if not match or match.group(1) != version:
        raise BuildFailure("VERSION and sazmanhr.__version__ do not match.")
    return version


def source_revision() -> str:
    github_sha = os.environ.get("GITHUB_SHA", "").strip()
    if re.fullmatch(r"[0-9a-fA-F]{40}", github_sha):
        return github_sha.lower()
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "uncommitted-source"


def write_build_manifest(
    *,
    version: str,
    seed_path: Path,
    seed_mode: str,
    executables: list[Path],
    signed: bool,
) -> None:
    artifacts = []
    for path in [*executables, INSTALLER]:
        artifacts.append({"name": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)})
    manifest = {
        "manifest_schema": 1,
        "product": "HRM",
        "version": version,
        "build_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_revision": source_revision(),
        "builder": {
            "os": platform.platform(),
            "python": platform.python_version(),
            "architecture": platform.machine(),
        },
        "seed": {"mode": seed_mode, "sha256": sha256(seed_path)},
        "signed": signed,
        "dependency_snapshot_sha256": sha256(DEPENDENCY_SNAPSHOT),
        "artifacts": artifacts,
    }
    BUILD_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def find_iscc() -> Path | None:
    candidates: list[Path] = []
    for variable in ("ProgramFiles(x86)", "ProgramFiles"):
        base = os.environ.get(variable)
        if base:
            candidates.append(Path(base) / "Inno Setup 6" / "ISCC.exe")
    local_app_data = os.environ.get("LocalAppData")
    if local_app_data:
        candidates.append(Path(local_app_data) / "Programs" / "Inno Setup 6" / "ISCC.exe")
    located = shutil.which("ISCC.exe") or shutil.which("iscc")
    if located:
        candidates.insert(0, Path(located))
    return next((path for path in candidates if path.is_file()), None)


def install_inno(log: BuildLog) -> Path:
    iscc = find_iscc()
    if iscc:
        return iscc
    winget = shutil.which("winget.exe") or shutil.which("winget")
    if not winget:
        raise BuildFailure(
            "Inno Setup 6 is missing and winget is unavailable. "
            "Ask IT to install Inno Setup 6, then run BUILD-SETUP.cmd again."
        )
    log.write("Inno Setup 6 was not found; installing it with winget...")
    run(
        log,
        [
            winget,
            "install",
            "--id",
            "JRSoftware.InnoSetup",
            "--exact",
            "--silent",
            "--accept-package-agreements",
            "--accept-source-agreements",
        ],
    )
    iscc = find_iscc()
    if not iscc:
        raise BuildFailure("Inno Setup installation finished, but ISCC.exe was not found.")
    return iscc


def find_signtool() -> Path | None:
    base = os.environ.get("ProgramFiles(x86)")
    if not base:
        return None
    kits = Path(base) / "Windows Kits" / "10" / "bin"
    if not kits.is_dir():
        return None
    matches = sorted(kits.glob("*/x64/signtool.exe"), reverse=True)
    return matches[0] if matches else None


def sign_files(log: BuildLog, files: Iterable[Path], thumbprint: str) -> None:
    signtool = find_signtool()
    if not signtool:
        raise BuildFailure("A signing thumbprint was supplied, but x64 signtool.exe was not found.")
    for path in files:
        run(
            log,
            [
                signtool,
                "sign",
                "/sha1",
                thumbprint,
                "/fd",
                "SHA256",
                "/tr",
                "http://timestamp.digicert.com",
                "/td",
                "SHA256",
                path,
            ],
        )


def prepare_output() -> BuildLog:
    if BUILD_ROOT.exists():
        try:
            shutil.rmtree(BUILD_ROOT)
        except OSError as exc:
            raise BuildFailure(
                f"Cannot clean {BUILD_ROOT}. Close running build tools or antivirus locks and retry: {exc}"
            ) from exc
    BUILD_ROOT.mkdir(parents=True, exist_ok=True)
    return BuildLog(LOG_PATH)


def build(log: BuildLog, *, sign_thumbprint: str = "", seed_path: Path | None = None) -> str:
    if platform.system() != "Windows":
        raise BuildFailure("The Setup builder must run on 64-bit Windows.")
    if sys.version_info[:2] != (3, 11) or sys.maxsize <= 2**32:
        raise BuildFailure("Python 3.11 x64 is required.")

    version = read_product_version()
    started = time.monotonic()
    log.write(f"HRM {version} Setup candidate build started.")
    log.write(f"Project: {PROJECT_ROOT}")
    log.write(f"Python: {sys.executable}")
    log.write(f"Windows: {platform.platform()}")

    run(log, [sys.executable, "-m", "venv", VENV_DIR])
    venv_python = VENV_DIR / "Scripts" / "python.exe"
    if not venv_python.is_file():
        raise BuildFailure(f"Virtual environment Python was not created: {venv_python}")

    run(log, [venv_python, "-m", "pip", "install", "--upgrade", "pip"])
    run(log, [venv_python, "-m", "pip", "install", "--only-binary=:all:", "-r", REQUIREMENTS])
    DEPENDENCY_SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    installed = capture(log, [venv_python, "-m", "pip", "freeze", "--all"])
    DEPENDENCY_SNAPSHOT.write_text(installed, encoding="utf-8", newline="\n")

    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(PROJECT_ROOT / "src")
    run(
        log,
        [venv_python, "-m", "unittest", "discover", "-s", PROJECT_ROOT / "tests", "-v"],
        env=environment,
    )

    if seed_path is None:
        seed_mode = "synthetic-demo"
        seed_path = BUILD_ROOT / "seed" / "hrm-seed.sqlite"
        run(
            log,
            [
                venv_python,
                PROJECT_ROOT / "tools" / "create_demo_seed.py",
                "--output",
                seed_path,
                "--force",
            ],
            env=environment,
        )
        log.write("Seed mode: synthetic demo data (safe for public CI artifacts).")
    else:
        seed_mode = "private-external"
        seed_path = seed_path.expanduser().resolve()
        log.write(f"Seed mode: externally supplied private seed ({seed_path.name}).")
    if not seed_path.is_file():
        raise BuildFailure(f"Seed database was not found: {seed_path}")

    for spec_name in ("client.spec", "server.spec", "service.spec"):
        run(
            log,
            [
                venv_python,
                "-m",
                "PyInstaller",
                "--noconfirm",
                "--clean",
                "--distpath",
                DIST_DIR,
                "--workpath",
                WORK_DIR,
                PROJECT_ROOT / "build" / "windows" / spec_name,
            ],
            env=environment,
        )

    executables = [
        DIST_DIR / "HRM.exe",
        DIST_DIR / "HRMServer.exe",
        DIST_DIR / "HRMService.exe",
    ]
    missing = [str(path) for path in executables if not path.is_file()]
    if missing:
        raise BuildFailure("PyInstaller output is incomplete: " + ", ".join(missing))

    # Import Qt and initialize the frozen GUI entry point without opening a window.
    # This catches missing Qt plugins/DLLs before the installer is compiled.
    run(log, [DIST_DIR / "HRM.exe", "--smoke-test"])

    # Execute the frozen server before creating Setup. This catches a missing
    # Python/cryptography/SQLite runtime inside the EXE on the actual build OS.
    smoke_data = BUILD_ROOT / "frozen-server-smoke-data"
    smoke_log = smoke_data / "logs" / "frozen-server-smoke.log"
    run(
        log,
        [
            DIST_DIR / "HRMServer.exe",
            "--data-dir",
            smoke_data,
            "--seed",
            seed_path,
            "--init-only",
            "--diagnostic-log",
            smoke_log,
        ],
    )
    run(
        log,
        [DIST_DIR / "HRMServer.exe", "--data-dir", smoke_data, "--verify-database"],
    )
    try:
        shutil.rmtree(smoke_data)
    except OSError as exc:
        raise BuildFailure(f"Frozen server left locked runtime data: {exc}") from exc

    if sign_thumbprint:
        sign_files(log, executables, sign_thumbprint)

    iscc = install_inno(log)
    log.write(f"Inno Setup: {iscc}")
    run(
        log,
        [
            iscc,
            f"/DProjectRoot={PROJECT_ROOT}",
            f"/DDistDir={DIST_DIR}",
            f"/DSeedPath={seed_path}",
            f"/DAppVersion={version}",
            INNO_SCRIPT,
        ],
    )
    if not INSTALLER.is_file():
        raise BuildFailure(f"Installer output was not created: {INSTALLER}")

    if sign_thumbprint:
        sign_files(log, [INSTALLER], sign_thumbprint)

    checksum = sha256(INSTALLER)
    checksum_file = INSTALLER.with_suffix(INSTALLER.suffix + ".sha256")
    checksum_file.write_text(f"{checksum}  {INSTALLER.name}\n", encoding="ascii")
    write_build_manifest(
        version=version,
        seed_path=seed_path,
        seed_mode=seed_mode,
        executables=executables,
        signed=bool(sign_thumbprint),
    )
    elapsed = time.monotonic() - started
    log.write(f"\nSetup ready: {INSTALLER}")
    log.write(f"SHA-256: {checksum}")
    log.write(f"Build duration: {elapsed:.1f} seconds")
    return checksum


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the HRM Windows Setup.")
    parser.add_argument("--launch", action="store_true", help="Open Setup after a successful build.")
    parser.add_argument("--sign-thumbprint", default="", help="Optional Windows code-signing certificate thumbprint.")
    parser.add_argument(
        "--seed",
        type=Path,
        help="Private production seed outside Git. Omit to build with synthetic demo data.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        log = prepare_output()
    except BuildFailure as exc:
        print(f"BUILD ERROR: {exc}", file=sys.stderr, flush=True)
        return 1
    try:
        build(log, sign_thumbprint=args.sign_thumbprint.strip(), seed_path=args.seed)
        if args.launch:
            log.write("Opening Setup. Approve the Windows UAC prompt to install.")
            subprocess.Popen([str(INSTALLER), f'/LOG={INSTALLER.parent / "install-test.log"}'])
        return 0
    except (BuildFailure, OSError) as exc:
        log.write(f"\nBUILD ERROR: {exc}")
        log.write(f"Diagnostic log: {LOG_PATH}")
        return 1
    except Exception as exc:  # keep unexpected failures visible and logged
        log.write(f"\nUNEXPECTED BUILD ERROR: {type(exc).__name__}: {exc}")
        log.write(f"Diagnostic log: {LOG_PATH}")
        return 1
    finally:
        log.close()


if __name__ == "__main__":
    raise SystemExit(main())
