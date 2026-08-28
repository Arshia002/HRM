#!/usr/bin/env python3
"""Native Windows builder for HRM.

This replaces the one-click PowerShell bootstrap so enterprise execution
policies cannot prevent the build before diagnostics are written.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BUILD_ROOT = PROJECT_ROOT / "build-output"
DIST_DIR = BUILD_ROOT / "dist"
WORK_DIR = BUILD_ROOT / "work"
VENV_DIR = BUILD_ROOT / "venv"
INSTALLER = BUILD_ROOT / "installer" / "HRM-Setup-x64.exe"
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


def sha256(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


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


def build(log: BuildLog, *, sign_thumbprint: str = "") -> str:
    if platform.system() != "Windows":
        raise BuildFailure("The Setup builder must run on 64-bit Windows.")
    if sys.version_info[:2] != (3, 11) or sys.maxsize <= 2**32:
        raise BuildFailure("Python 3.11 x64 is required.")

    started = time.monotonic()
    log.write("HRM 0.2.0-alpha.2 direct Setup candidate build started.")
    log.write(f"Project: {PROJECT_ROOT}")
    log.write(f"Python: {sys.executable}")
    log.write(f"Windows: {platform.platform()}")

    run(log, [sys.executable, "-m", "venv", VENV_DIR])
    venv_python = VENV_DIR / "Scripts" / "python.exe"
    if not venv_python.is_file():
        raise BuildFailure(f"Virtual environment Python was not created: {venv_python}")

    # Validate names, installer inputs, versions and public-safe seed before
    # spending time on dependency installation or PyInstaller.  This is the
    # guard that prevents a repeat of the alpha.1 SazmanHR.exe/HRM.exe mismatch.
    run(log, [sys.executable, PROJECT_ROOT / "ci" / "validate_package_contract.py"])

    run(log, [venv_python, "-m", "pip", "install", "--upgrade", "pip"])
    run(log, [venv_python, "-m", "pip", "install", "-r", REQUIREMENTS])

    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(PROJECT_ROOT / "src")
    run(
        log,
        [venv_python, "-m", "unittest", "discover", "-s", PROJECT_ROOT / "tests", "-v"],
        env=environment,
    )

    spec_outputs = (
        ("client.spec", "HRM.exe"),
        ("server.spec", "HRMServer.exe"),
        ("service.spec", "HRMService.exe"),
    )
    for spec_name, output_name in spec_outputs:
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
        expected_output = DIST_DIR / output_name
        if not expected_output.is_file():
            produced = ", ".join(sorted(path.name for path in DIST_DIR.glob("*.exe"))) or "<none>"
            raise BuildFailure(
                f"PyInstaller contract failed after {spec_name}: expected {expected_output}; "
                f"produced executables: {produced}"
            )
        log.write(f"PASS PyInstaller contract: {spec_name} -> {output_name}")

    executables = [DIST_DIR / output_name for _, output_name in spec_outputs]
    missing = [str(path) for path in executables if not path.is_file()]
    if missing:
        raise BuildFailure("PyInstaller output is incomplete: " + ", ".join(missing))

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
            PROJECT_ROOT / "data" / "seed" / "sazmanhr-seed.sqlite",
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
    elapsed = time.monotonic() - started
    log.write(f"\nSetup ready: {INSTALLER}")
    log.write(f"SHA-256: {checksum}")
    log.write(f"Build duration: {elapsed:.1f} seconds")
    return checksum


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the HRM Windows Setup.")
    parser.add_argument("--launch", action="store_true", help="Open Setup after a successful build.")
    parser.add_argument("--sign-thumbprint", default="", help="Optional Windows code-signing certificate thumbprint.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        log = prepare_output()
    except BuildFailure as exc:
        print(f"BUILD ERROR: {exc}", file=sys.stderr, flush=True)
        return 1
    try:
        build(log, sign_thumbprint=args.sign_thumbprint.strip())
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
