"""Small, dependency-free Windows Service control used by Setup preflight."""

from __future__ import annotations

import locale
import ntpath
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Callable

SERVICE_STOPPED = 1
SERVICE_START_PENDING = 2
SERVICE_STOP_PENDING = 3
SERVICE_RUNNING = 4
ERROR_SERVICE_DOES_NOT_EXIST = 1060
ERROR_SERVICE_ALREADY_RUNNING = 1056
ERROR_SERVICE_NOT_ACTIVE = 1062
ERROR_SERVICE_MARKED_FOR_DELETE = 1072
SERVICE_NAME_PATTERN = re.compile(r"[A-Za-z0-9_.-]{1,128}\Z")
STATE_PATTERN = re.compile(r"(?m)^\s*[^:\r\n]+:\s*([1-7])\s{2,}[^\r\n]*$")
ScRunner = Callable[[str, str], tuple[int, str]]
ServiceImageReader = Callable[[str], str | None]
ServiceImageChanger = Callable[[str, str], None]


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



def _service_executable_from_image_path(image_path: str) -> str:
    value = image_path.strip()
    if not value:
        return ""
    if value.startswith('"'):
        closing = value.find('"', 1)
        if closing <= 1:
            return ""
        return value[1:closing]
    return value


def _read_service_image_path(service_name: str) -> str | None:
    if os.name != "nt":
        raise RuntimeError("Windows Service configuration is only available on Windows.")
    import winreg

    key_path = rf"SYSTEM\\CurrentControlSet\\Services\\{service_name}"
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
            value, value_type = winreg.QueryValueEx(key, "ImagePath")
    except FileNotFoundError:
        return None
    if value_type not in (winreg.REG_SZ, winreg.REG_EXPAND_SZ):
        raise RuntimeError(
            f"Windows Service {service_name!r} ImagePath has unexpected registry type {value_type}."
        )
    return str(value)


def _change_service_image_path(service_name: str, image_path: str) -> None:
    if os.name != "nt":
        raise RuntimeError("Windows Service configuration is only available on Windows.")
    import ctypes
    from ctypes import wintypes

    advapi32 = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    advapi32.OpenSCManagerW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
    advapi32.OpenSCManagerW.restype = wintypes.HANDLE
    advapi32.OpenServiceW.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR, wintypes.DWORD]
    advapi32.OpenServiceW.restype = wintypes.HANDLE
    advapi32.ChangeServiceConfigW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        ctypes.POINTER(wintypes.DWORD),
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
    ]
    advapi32.ChangeServiceConfigW.restype = wintypes.BOOL
    advapi32.CloseServiceHandle.argtypes = [wintypes.HANDLE]
    advapi32.CloseServiceHandle.restype = wintypes.BOOL

    SC_MANAGER_CONNECT = 0x0001
    SERVICE_CHANGE_CONFIG = 0x0002
    SERVICE_NO_CHANGE = 0xFFFFFFFF

    scm = advapi32.OpenSCManagerW(None, None, SC_MANAGER_CONNECT)
    if not scm:
        raise ctypes.WinError(ctypes.get_last_error())
    service = None
    try:
        service = advapi32.OpenServiceW(scm, service_name, SERVICE_CHANGE_CONFIG)
        if not service:
            raise ctypes.WinError(ctypes.get_last_error())
        if not advapi32.ChangeServiceConfigW(
            service,
            SERVICE_NO_CHANGE,
            SERVICE_NO_CHANGE,
            SERVICE_NO_CHANGE,
            image_path,
            None,
            None,
            None,
            None,
            None,
            None,
        ):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        if service:
            advapi32.CloseServiceHandle(service)
        advapi32.CloseServiceHandle(scm)


def set_windows_service_binary_path(
    service_name: str,
    executable_path: str | Path,
    *,
    reader: ServiceImageReader | None = None,
    changer: ServiceImageChanger | None = None,
) -> dict[str, object]:
    """Switch SCM ImagePath using ChangeServiceConfigW and verify the result."""
    if not SERVICE_NAME_PATTERN.fullmatch(service_name):
        raise ValueError("Windows Service name is invalid.")
    executable = str(executable_path).strip()
    if (
        not executable
        or not ntpath.isabs(executable)
        or '"' in executable
        or "\r" in executable
        or "\n" in executable
    ):
        raise ValueError("Windows Service executable path must be an absolute unquoted path.")
    reader = reader or _read_service_image_path
    changer = changer or _change_service_image_path

    before = reader(service_name)
    if before is None:
        raise RuntimeError(f"Windows Service {service_name!r} does not exist.")
    desired = f'"{executable}"'
    changer(service_name, desired)
    after = reader(service_name)
    if after is None:
        raise RuntimeError(f"Windows Service {service_name!r} disappeared while changing ImagePath.")
    actual = _service_executable_from_image_path(after)
    if ntpath.normcase(ntpath.normpath(actual)) != ntpath.normcase(ntpath.normpath(executable)):
        raise RuntimeError(
            f"Windows Service {service_name!r} ImagePath verification failed: {after!r}"
        )
    return {
        "exists": True,
        "image_path_before": before,
        "image_path_after": after,
        "executable": actual,
    }


def delete_windows_service(
    service_name: str,
    *,
    runner: ScRunner | None = None,
) -> dict[str, object]:
    """Delete a stopped service; an already-missing service is success."""
    if not SERVICE_NAME_PATTERN.fullmatch(service_name):
        raise ValueError("Windows Service name is invalid.")
    if runner is None:
        if os.name != "nt":
            raise RuntimeError("Windows Service control is only available on Windows.")
        runner = _run_sc
    state = _query_state(service_name, runner)
    if state is None:
        return {"exists": False, "deleted": False}
    if state != SERVICE_STOPPED:
        raise RuntimeError(
            f"Windows Service {service_name!r} must be STOPPED before deletion (state {state})."
        )
    return_code, output = runner("delete", service_name)
    if return_code and not (
        _contains_service_error(return_code, output, ERROR_SERVICE_DOES_NOT_EXIST)
        or _contains_service_error(return_code, output, ERROR_SERVICE_MARKED_FOR_DELETE)
    ):
        raise RuntimeError(
            f"Unable to delete Windows Service {service_name!r} (exit {return_code}): "
            f"{output.strip()[-1000:]}"
        )
    return {"exists": True, "deleted": True}


def start_windows_service(
    service_name: str,
    timeout_seconds: float = 30,
    *,
    runner: ScRunner | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, object]:
    """Start a service and prove SCM reports RUNNING before returning."""
    if not SERVICE_NAME_PATTERN.fullmatch(service_name):
        raise ValueError("Windows Service name is invalid.")
    if timeout_seconds <= 0:
        raise ValueError("Service start timeout must be positive.")
    if runner is None:
        if os.name != "nt":
            raise RuntimeError("Windows Service control is only available on Windows.")
        runner = _run_sc

    deadline = clock() + timeout_seconds
    initial_state = _query_state(service_name, runner)
    if initial_state is None:
        raise RuntimeError(f"Windows Service {service_name!r} does not exist.")
    if initial_state == SERVICE_RUNNING:
        return {
            "exists": True,
            "was_running": True,
            "initial_state": SERVICE_RUNNING,
            "final_state": SERVICE_RUNNING,
        }

    current_state = initial_state
    if current_state == SERVICE_STOP_PENDING:
        while current_state == SERVICE_STOP_PENDING:
            if clock() >= deadline:
                raise TimeoutError(
                    f"Windows Service {service_name!r} remained STOP_PENDING for "
                    f"{timeout_seconds:g} seconds."
                )
            sleeper(0.25)
            current_state = _query_state(service_name, runner)
            if current_state is None:
                raise RuntimeError(f"Windows Service {service_name!r} disappeared while stopping.")

    if current_state == SERVICE_STOPPED:
        return_code, output = runner("start", service_name)
        if return_code and not _contains_service_error(
            return_code, output, ERROR_SERVICE_ALREADY_RUNNING
        ):
            raise RuntimeError(
                f"Unable to start Windows Service {service_name!r} (exit {return_code}): "
                f"{output.strip()[-1000:]}"
            )
    elif current_state != SERVICE_START_PENDING:
        raise RuntimeError(
            f"Windows Service {service_name!r} is in unsupported start state {current_state}."
        )

    while True:
        current_state = _query_state(service_name, runner)
        if current_state == SERVICE_RUNNING:
            return {
                "exists": True,
                "was_running": False,
                "initial_state": initial_state,
                "final_state": SERVICE_RUNNING,
            }
        if current_state in (None, SERVICE_STOPPED):
            raise RuntimeError(
                f"Windows Service {service_name!r} stopped before reaching RUNNING "
                f"(state {current_state})."
            )
        if clock() >= deadline:
            raise TimeoutError(
                f"Windows Service {service_name!r} did not reach RUNNING within "
                f"{timeout_seconds:g} seconds (state {current_state})."
            )
        sleeper(0.25)

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
        if return_code and not _contains_service_error(return_code, output, ERROR_SERVICE_NOT_ACTIVE):
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
