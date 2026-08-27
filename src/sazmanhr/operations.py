"""Operational logging, scheduled backups and offline restore."""

from __future__ import annotations

import contextlib
import datetime as dt
import json
import logging
import logging.handlers
import os
import shutil
import sqlite3
import threading
from pathlib import Path

from .config import validate_database_identity
from .database import Repository


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        standard = {"name", "msg", "args", "levelname", "levelno", "pathname", "filename", "module",
                    "exc_info", "exc_text", "stack_info", "lineno", "funcName", "created", "msecs",
                    "relativeCreated", "thread", "threadName", "processName", "process", "taskName"}
        for key, value in record.__dict__.items():
            if key not in standard and not key.startswith("_"):
                try:
                    json.dumps(value)
                    payload[key] = value
                except TypeError:
                    payload[key] = repr(value)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging(data_dir: Path, level: str = "INFO") -> logging.Logger:
    log_dir = data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("sazmanhr")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False
    close_logging(logger)
    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "server.jsonl", maxBytes=10 * 1024 * 1024, backupCount=10, encoding="utf-8"
    )
    file_handler.setFormatter(JsonFormatter())
    logger.addHandler(file_handler)
    console = logging.StreamHandler()
    console.setFormatter(JsonFormatter())
    logger.addHandler(console)
    return logger


def close_logging(logger: logging.Logger | None) -> None:
    """Flush, detach and close every handler owned by the server logger.

    Clearing ``logger.handlers`` alone leaks the open RotatingFileHandler on
    Windows and prevents Setup/tests from deleting ``server.jsonl``.
    """
    if logger is None:
        return
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        try:
            handler.flush()
        finally:
            handler.close()


def sqlite_integrity(path: Path) -> tuple[bool, str]:
    if not path.is_file():
        return False, "file_not_found"
    try:
        with contextlib.closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as conn:
            result = conn.execute("PRAGMA integrity_check").fetchone()[0]
        return result == "ok", str(result)
    except sqlite3.Error as exc:
        return False, repr(exc)


def restore_database(database_path: Path, backup_path: Path) -> Path:
    ok, detail = sqlite_integrity(backup_path)
    if not ok:
        raise RuntimeError(f"Backup integrity failed: {detail}")
    validate_database_identity(backup_path)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    safety = database_path.with_name(f"{database_path.stem}-before-restore-{stamp}.sqlite")
    if database_path.exists():
        with (
            contextlib.closing(sqlite3.connect(database_path)) as current,
            contextlib.closing(sqlite3.connect(safety)) as safe_copy,
        ):
            current.backup(safe_copy)
    staged = database_path.with_suffix(".restore-staged")
    shutil.copy2(backup_path, staged)
    ok, detail = sqlite_integrity(staged)
    if not ok:
        staged.unlink(missing_ok=True)
        raise RuntimeError(f"Staged restore failed: {detail}")
    validate_database_identity(staged)
    os.replace(staged, database_path)
    for suffix in ("-wal", "-shm"):
        database_path.with_name(database_path.name + suffix).unlink(missing_ok=True)
    return safety


class BackupScheduler:
    def __init__(self, repository: Repository, interval_hours: int = 24, retention: int = 30):
        self.repository = repository
        self.interval_seconds = max(1, interval_hours) * 3600
        self.retention = retention
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="sazmanhr-backup", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=10)

    def run_once(self) -> Path:
        backup_dir = self.repository.path.parent / "backups"
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        target = self.repository.backup(backup_dir / f"scheduled-{stamp}.sqlite", kind="scheduled")
        self.repository.prune_backups(backup_dir, self.retention)
        self.repository.record_operational("INFO", "backup", "backup_ok", "Scheduled backup completed",
                                           {"filename": target.name})
        return target

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            try:
                self.run_once()
            except Exception as exc:
                try:
                    self.repository.record_operational("ERROR", "backup", "backup_failed", repr(exc))
                except Exception:
                    pass
