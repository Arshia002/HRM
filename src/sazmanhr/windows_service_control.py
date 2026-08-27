"""Small, dependency-free Windows Service control used by Setup preflight."""

from __future__ import annotations

import locale
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Callable


SERVICE_STOPPED = 1
SERVICE_STOP_PENDING = 3
ERROR_SERVICE_DOES_NOT_EXIST = 1060
ERROR_SERVICE_NOT_ACTIVE = 1062
SERVICE_NAME_PATTERN = re.compile(r"[A-Za-z0-9_.-]{1,128}\Z")
STATE_PATTERN = re.compile(r"(?m)^\s*[^:\r\n]+:\s*([1-7])\s{2,}[^\r\n]*$")

ScRunner = Callable[[str, str], tuple[int, str]]


def _sc_executable() -> str:
    system_root = os.environ.get("SystemRoot", "")
    candidate = Path(system_root) / "System32" / "sc.exe" if system_root else None
    return str(candidate) if candidate and candidate.is_file() else "sc.exe"


def _run_sc(action: str, service_name: str) -> tuple[int, str]:
    completed = subprocess.run(
        [_sc_executable(), action, service_name],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding=locale.getpreferredencoding(False) or "utf-8",
        errors="replace",
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return completed.returncode, completed.stdout


def _contains_service_error(return_code: int, output: str, error_code: int) -> bool:
    return return_code == error_code or re.search(rf"\b{error_code}\b", output) is not None


def _query_state(service_name: str, runner: ScRunner) -> int | None:
    return_code, output = runner("queryex", service_name)
    if return_code:
        if _contains_service_error(return_code, output, ERROR_SERVICE_DOES_NOT_EXIST):
            return None
        raise RuntimeError(
            f"Unable to query Windows Service {service_name!r} (exit {return_code}): "
            f"{output.strip()[-1000:]}"
        )
    match = STATE_PATTERN.search(output)
    if not match:
        raise RuntimeError(f"Unable to parse Windows Service state: {output.strip()[-1000:]}")
    return int(match.group(1))


def stop_windows_service(
    service_name: str,
    timeout_seconds: float = 30,
    *,
    runner: ScRunner | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, object]:
    """Stop a service and prove SCM reports STOPPED before returning."""
    if not SERVICE_NAME_PATTERN.fullmatch(service_name):
        raise ValueError("Windows Service name is invalid.")
    if timeout_seconds <= 0:
        raise ValueError("Service stop timeout must be positive.")
    if runner is None:
        if os.name != "nt":
            raise RuntimeError("Windows Service control is only available on Windows.")
        runner = _run_sc

    initial_state = _query_state(service_name, runner)
    if initial_state is None:
        return {"exists": False, "was_running": False, "initial_state": None, "final_state": None}
    if initial_state == SERVICE_STOPPED:
        return {
            "exists": True,
            "was_running": False,
            "initial_state": SERVICE_STOPPED,
            "final_state": SERVICE_STOPPED,
        }

    if initial_state != SERVICE_STOP_PENDING:
        return_code, output = runner("stop", service_name)
        if return_code and not _contains_service_error(
            return_code, output, ERROR_SERVICE_NOT_ACTIVE
        ):
            raise RuntimeError(
                f"Unable to stop Windows Service {service_name!r} (exit {return_code}): "
                f"{output.strip()[-1000:]}"
            )

    deadline = clock() + timeout_seconds
    while True:
        current_state = _query_state(service_name, runner)
        if current_state in (None, SERVICE_STOPPED):
            return {
                "exists": True,
                "was_running": True,
                "initial_state": initial_state,
                "final_state": current_state,
            }
        if clock() >= deadline:
            raise TimeoutError(
                f"Windows Service {service_name!r} did not stop within {timeout_seconds:g} seconds "
                f"(state {current_state})."
            )
        sleeper(0.25)
