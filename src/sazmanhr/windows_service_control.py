"""Small, dependency-free Windows Service control used by Setup preflight."""

from __future__ import annotations

import json
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
ServiceConfigurationReader = Callable[[str], dict[str, object]]
ServiceStateReader = Callable[[str], int | None]

SERVICE_CUTOVER_JOURNAL_SCHEMA = 1
SERVICE_CUTOVER_PHASES = (
    "snapshotted",
    "service_stopped",
    "image_switched",
    "service_started",
    "ready",
    "committed",
    "recovered",
)
_SERVICE_CUTOVER_REQUIRED_FIELDS = (
    "schema",
    "service_name",
    "original_image_path",
    "original_executable",
    "original_start_type",
    "original_object_name",
    "original_sid_type",
    "was_running",
    "target_executable",
    "phase",
    "committed",
)


def _validate_service_cutover_journal(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise RuntimeError("Service cutover journal is invalid.")
    missing = [name for name in _SERVICE_CUTOVER_REQUIRED_FIELDS if name not in payload]
    if missing:
        raise RuntimeError(
            "Service cutover journal is incomplete: missing " + ", ".join(missing)
        )

    if payload.get("schema") != SERVICE_CUTOVER_JOURNAL_SCHEMA:
        raise RuntimeError("Service cutover journal schema is invalid.")

    service_name = payload.get("service_name")
    if not isinstance(service_name, str) or not SERVICE_NAME_PATTERN.fullmatch(service_name):
        raise RuntimeError("Service cutover journal service name is invalid.")

    for field in (
        "original_image_path",
        "original_executable",
        "original_object_name",
        "target_executable",
    ):
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip() or "\r" in value or "\n" in value:
            raise RuntimeError(f"Service cutover journal field {field!r} is invalid.")

    for field in ("original_executable", "target_executable"):
        value = str(payload[field]).strip()
        if not ntpath.isabs(value) or '"' in value:
            raise RuntimeError(
                f"Service cutover journal field {field!r} must be an absolute unquoted path."
            )

    start_type = payload.get("original_start_type")
    if isinstance(start_type, bool) or not isinstance(start_type, int) or start_type not in (2, 3, 4):
        raise RuntimeError("Service cutover journal original start type is invalid.")

    sid_type = payload.get("original_sid_type")
    if (
        isinstance(sid_type, bool)
        or not isinstance(sid_type, int)
        or sid_type not in (0, 1, 3)
    ):
        raise RuntimeError("Service cutover journal original SID type is invalid.")

    if not isinstance(payload.get("was_running"), bool):
        raise RuntimeError("Service cutover journal running-state flag is invalid.")

    phase = payload.get("phase")
    if phase not in SERVICE_CUTOVER_PHASES:
        raise RuntimeError("Service cutover journal phase is invalid.")

    committed = payload.get("committed")
    if not isinstance(committed, bool):
        raise RuntimeError("Service cutover journal commit flag is invalid.")
    if committed != (phase == "committed"):
        raise RuntimeError("Service cutover journal commit state is invalid.")

    return dict(payload)


def _replace_state_file(staged: Path, destination: Path) -> None:
    if os.name != "nt":
        os.replace(staged, destination)
        return

    import ctypes

    MOVEFILE_REPLACE_EXISTING = 0x1
    MOVEFILE_WRITE_THROUGH = 0x8
    kernel32 = ctypes.WinDLL("Kernel32.dll", use_last_error=True)
    kernel32.MoveFileExW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint]
    kernel32.MoveFileExW.restype = ctypes.c_int
    if not kernel32.MoveFileExW(
        str(staged),
        str(destination),
        MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH,
    ):
        raise ctypes.WinError(ctypes.get_last_error())


def _write_service_cutover_journal(
    state_path: Path,
    payload: dict[str, object],
) -> dict[str, object]:
    state_path = Path(state_path).resolve()
    validated = _validate_service_cutover_journal(payload)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    staged = state_path.with_suffix(state_path.suffix + ".staged")
    staged.unlink(missing_ok=True)

    raw = json.dumps(
        validated,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    try:
        with staged.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        _replace_state_file(staged, state_path)
        with state_path.open("r+b") as handle:
            os.fsync(handle.fileno())
    finally:
        staged.unlink(missing_ok=True)

    return validated


def load_service_cutover_journal(state_path: Path) -> dict[str, object]:
    state_path = Path(state_path).resolve()
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("Service cutover journal is invalid.") from exc
    return _validate_service_cutover_journal(payload)


def create_service_cutover_journal(
    state_path: Path,
    snapshot: dict[str, object],
) -> dict[str, object]:
    state_path = Path(state_path).resolve()
    if state_path.exists():
        existing = load_service_cutover_journal(state_path)
        if not bool(existing["committed"]) and existing["phase"] != "recovered":
            raise RuntimeError(
                "Refusing to overwrite an uncommitted service cutover journal."
            )

    payload = dict(snapshot)
    payload.update(
        {
            "schema": SERVICE_CUTOVER_JOURNAL_SCHEMA,
            "phase": "snapshotted",
            "committed": False,
        }
    )
    return _write_service_cutover_journal(state_path, payload)


def advance_service_cutover_journal(
    state_path: Path,
    phase: str,
) -> dict[str, object]:
    state = load_service_cutover_journal(state_path)
    if bool(state["committed"]):
        raise RuntimeError("Service cutover journal transition is invalid after commit.")
    if phase in ("committed", "recovered") or phase not in SERVICE_CUTOVER_PHASES:
        raise RuntimeError("Service cutover journal transition is invalid.")

    current = str(state["phase"])
    current_index = SERVICE_CUTOVER_PHASES.index(current)
    target_index = SERVICE_CUTOVER_PHASES.index(phase)
    if target_index != current_index + 1:
        raise RuntimeError(
            f"Service cutover journal transition is invalid: {current!r} -> {phase!r}."
        )

    updated = dict(state)
    updated["phase"] = phase
    return _write_service_cutover_journal(state_path, updated)


def mark_service_cutover_committed(state_path: Path) -> dict[str, object]:
    state = load_service_cutover_journal(state_path)
    if bool(state["committed"]):
        return state
    if state["phase"] != "ready":
        raise RuntimeError(
            f"Service cutover journal transition is invalid: {state['phase']!r} -> 'committed'."
        )

    updated = dict(state)
    updated["phase"] = "committed"
    updated["committed"] = True
    return _write_service_cutover_journal(state_path, updated)


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


def _read_service_configuration(service_name: str) -> dict[str, object]:
    if os.name != "nt":
        raise RuntimeError("Windows Service configuration is only available on Windows.")
    if not SERVICE_NAME_PATTERN.fullmatch(service_name):
        raise ValueError("Windows Service name is invalid.")

    import winreg

    key_path = rf"SYSTEM\CurrentControlSet\Services\{service_name}"
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
            image_path, image_type = winreg.QueryValueEx(key, "ImagePath")
            start_type, start_value_type = winreg.QueryValueEx(key, "Start")
            object_name, object_value_type = winreg.QueryValueEx(key, "ObjectName")
            try:
                sid_type, sid_value_type = winreg.QueryValueEx(key, "ServiceSidType")
            except FileNotFoundError:
                sid_type, sid_value_type = 0, winreg.REG_DWORD
    except FileNotFoundError as exc:
        raise RuntimeError(f"Windows Service {service_name!r} does not exist.") from exc

    if image_type not in (winreg.REG_SZ, winreg.REG_EXPAND_SZ):
        raise RuntimeError("Windows Service configuration ImagePath type is invalid.")
    if start_value_type != winreg.REG_DWORD:
        raise RuntimeError("Windows Service configuration Start type is invalid.")
    if object_value_type not in (winreg.REG_SZ, winreg.REG_EXPAND_SZ):
        raise RuntimeError("Windows Service configuration ObjectName type is invalid.")
    if sid_value_type != winreg.REG_DWORD:
        raise RuntimeError("Windows Service configuration ServiceSidType type is invalid.")

    return {
        "image_path": str(image_path),
        "start_type": int(start_type),
        "object_name": str(object_name),
        "sid_type": int(sid_type),
    }


def create_windows_service_cutover_journal(
    state_path: Path,
    service_name: str,
    target_executable: str | Path,
    *,
    configuration_reader: ServiceConfigurationReader | None = None,
    state_reader: ServiceStateReader | None = None,
) -> dict[str, object]:
    if not SERVICE_NAME_PATTERN.fullmatch(service_name):
        raise ValueError("Windows Service name is invalid.")

    target = str(target_executable).strip()
    if (
        not target
        or not ntpath.isabs(target)
        or '"' in target
        or "\r" in target
        or "\n" in target
    ):
        raise ValueError("Windows Service target executable must be an absolute unquoted path.")

    configuration_reader = configuration_reader or _read_service_configuration
    if state_reader is None:
        if os.name != "nt":
            raise RuntimeError("Windows Service control is only available on Windows.")
        state_reader = lambda name: _query_state(name, _run_sc)

    state = state_reader(service_name)
    if state is None:
        raise RuntimeError(f"Windows Service {service_name!r} does not exist.")
    if state not in (SERVICE_STOPPED, SERVICE_RUNNING):
        raise RuntimeError(
            f"Windows Service {service_name!r} must be stable before cutover snapshot "
            f"(state {state})."
        )

    try:
        config = configuration_reader(service_name)
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError("Windows Service configuration could not be read.") from exc

    if not isinstance(config, dict):
        raise RuntimeError("Windows Service configuration is invalid.")

    image_path = config.get("image_path")
    start_type = config.get("start_type")
    object_name = config.get("object_name")
    sid_type = config.get("sid_type")

    if not isinstance(image_path, str) or not image_path.strip():
        raise RuntimeError("Windows Service configuration ImagePath is invalid.")
    original_executable = _service_executable_from_image_path(image_path)
    if (
        not original_executable
        or not ntpath.isabs(original_executable)
        or '"' in original_executable
        or "\r" in original_executable
        or "\n" in original_executable
    ):
        raise RuntimeError("Windows Service configuration executable is invalid.")

    if isinstance(start_type, bool) or not isinstance(start_type, int) or start_type not in (2, 3, 4):
        raise RuntimeError("Windows Service configuration Start value is invalid.")
    if not isinstance(object_name, str) or not object_name.strip():
        raise RuntimeError("Windows Service configuration ObjectName is invalid.")
    if object_name.strip().lower() != r"nt authority\localservice":
        raise RuntimeError(
            "Windows Service configuration account is unsupported for transactional recovery."
        )
    if (
        isinstance(sid_type, bool)
        or not isinstance(sid_type, int)
        or sid_type not in (0, 1, 3)
    ):
        raise RuntimeError("Windows Service configuration ServiceSidType is invalid.")

    snapshot = {
        "service_name": service_name,
        "original_image_path": image_path,
        "original_executable": original_executable,
        "original_start_type": start_type,
        "original_object_name": object_name,
        "original_sid_type": sid_type,
        "was_running": state == SERVICE_RUNNING,
        "target_executable": target,
    }
    return create_service_cutover_journal(Path(state_path), snapshot)


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


def restore_windows_service_configuration(
    service_name: str,
    *,
    start_type: int,
    object_name: str,
    sid_type: int,
) -> dict[str, object]:
    if not SERVICE_NAME_PATTERN.fullmatch(service_name):
        raise ValueError("Windows Service name is invalid.")
    if start_type not in (2, 3, 4):
        raise ValueError("Windows Service start type is invalid.")
    if object_name.strip().lower() != r"nt authority\localservice":
        raise ValueError(
            "Only NT AUTHORITY\\LocalService is supported for transactional recovery."
        )
    if sid_type not in (0, 1, 3):
        raise ValueError("Windows Service SID type is invalid.")
    if os.name != "nt":
        raise RuntimeError("Windows Service configuration is only available on Windows.")

    start_mode = {2: "auto", 3: "demand", 4: "disabled"}[start_type]
    sid_mode = {0: "none", 1: "unrestricted", 3: "restricted"}[sid_type]

    config = subprocess.run(
        [
            _sc_executable(),
            "config",
            service_name,
            "start=",
            start_mode,
            "obj=",
            r"NT AUTHORITY\LocalService",
            "password=",
            "",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding=locale.getpreferredencoding(False) or "utf-8",
        errors="replace",
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if config.returncode:
        raise RuntimeError(
            f"Unable to restore Windows Service configuration {service_name!r} "
            f"(exit {config.returncode}): {config.stdout.strip()[-1000:]}"
        )

    sid = subprocess.run(
        [_sc_executable(), "sidtype", service_name, sid_mode],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding=locale.getpreferredencoding(False) or "utf-8",
        errors="replace",
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if sid.returncode:
        raise RuntimeError(
            f"Unable to restore Windows Service SID type {service_name!r} "
            f"(exit {sid.returncode}): {sid.stdout.strip()[-1000:]}"
        )

    actual = _read_service_configuration(service_name)
    if int(actual["start_type"]) != start_type:
        raise RuntimeError("Windows Service start type verification failed after recovery.")
    if str(actual["object_name"]).strip().lower() != r"nt authority\localservice":
        raise RuntimeError("Windows Service account verification failed after recovery.")
    if int(actual["sid_type"]) != sid_type:
        raise RuntimeError("Windows Service SID type verification failed after recovery.")

    return {
        "ok": True,
        "service_name": service_name,
        "start_type": start_type,
        "object_name": str(actual["object_name"]),
        "sid_type": sid_type,
    }


def recover_windows_service_cutover(
    state_path: Path,
    *,
    stopper=None,
    image_setter=None,
    configuration_restorer=None,
    starter=None,
) -> dict[str, object]:
    state_path = Path(state_path).resolve()
    state = load_service_cutover_journal(state_path)

    if bool(state["committed"]) or state["phase"] == "committed":
        return state
    if state["phase"] == "recovered":
        return state

    stopper = stopper or stop_windows_service
    image_setter = image_setter or set_windows_service_binary_path
    configuration_restorer = configuration_restorer or restore_windows_service_configuration
    starter = starter or start_windows_service

    service_name = str(state["service_name"])
    original_executable = str(state["original_executable"])

    stopper(service_name)
    image_setter(service_name, original_executable)
    configuration_restorer(
        service_name,
        start_type=int(state["original_start_type"]),
        object_name=str(state["original_object_name"]),
        sid_type=int(state["original_sid_type"]),
    )

    if bool(state["was_running"]):
        starter(service_name)

    recovered = dict(state)
    recovered["phase"] = "recovered"
    recovered["committed"] = False
    return _write_service_cutover_journal(state_path, recovered)


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
