"""Runtime paths and server/client configuration."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import contextlib
from dataclasses import dataclass
from pathlib import Path


PRODUCT_ID = "hrm-kepdco"
SCHEMA_GENERATION = "1"
WINDOWS_DATA_DIRECTORY = "HRM-Kermanshah"
DATABASE_FILENAME = "hrm.sqlite"


class IncompatibleDatabaseError(RuntimeError):
    """Raised before any incompatible or legacy database can be modified."""


def validate_database_identity(path: Path) -> None:
    """Accept only databases created for this clean enterprise generation."""
    if not path.is_file():
        raise IncompatibleDatabaseError(f"Database file does not exist: {path}")
    try:
        # sqlite3.Connection.__exit__ commits/rolls back but does not close.
        # An unclosed validation handle prevents TemporaryDirectory and Setup
        # cleanup on Windows, so closing must be explicit.
        with contextlib.closing(sqlite3.connect(path)) as conn:
            rows = dict(conn.execute(
                "SELECT key,value FROM metadata WHERE key IN ('product_id','schema_generation')"
            ))
    except sqlite3.Error as exc:
        raise IncompatibleDatabaseError(
            "Database is not a valid HRM database."
        ) from exc
    if rows.get("product_id") != PRODUCT_ID or rows.get("schema_generation") != SCHEMA_GENERATION:
        raise IncompatibleDatabaseError(
            "Legacy or incompatible database was blocked. "
            f"Expected product_id={PRODUCT_ID!r} and schema_generation={SCHEMA_GENERATION!r}."
        )


def default_data_dir() -> Path:
    configured = os.environ.get("HRM_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    program_data = os.environ.get("PROGRAMDATA")
    if os.name == "nt" and program_data:
        return Path(program_data) / WINDOWS_DATA_DIRECTORY
    return Path.home() / ".local" / "share" / "hrm-kermanshah"


def default_client_config() -> Path:
    app_data = os.environ.get("APPDATA")
    if os.name == "nt" and app_data:
        return Path(app_data) / WINDOWS_DATA_DIRECTORY / "client.json"
    return Path.home() / ".config" / "hrm-kermanshah" / "client.json"


def bundled_seed_path() -> Path | None:
    sys_module = __import__("sys")
    candidates = [
        Path(__file__).resolve().parents[2] / "data" / "seed" / "hrm-seed.sqlite",
        Path(getattr(sys_module, "_MEIPASS", "")) / "data" / "seed" / "hrm-seed.sqlite",
        Path(sys_module.executable).resolve().parent / "data" / "seed" / "hrm-seed.sqlite",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def ensure_database(data_dir: Path, explicit_seed: Path | None = None) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / DATABASE_FILENAME
    if db_path.exists():
        validate_database_identity(db_path)
        return db_path
    seed = explicit_seed or bundled_seed_path()
    if not seed or not seed.is_file():
        raise FileNotFoundError("The HRM seed database is missing.")
    validate_database_identity(seed)
    shutil.copy2(seed, db_path)
    try:
        validate_database_identity(db_path)
    except Exception:
        db_path.unlink(missing_ok=True)
        raise
    return db_path


@dataclass(slots=True)
class ClientConfig:
    server_url: str = "https://127.0.0.1:8765"
    poll_seconds: int = 3
    tls_fingerprint: str = ""

    @classmethod
    def load(cls, path: Path | None = None) -> "ClientConfig":
        target = path or default_client_config()
        if not target.exists():
            return cls()
        data = json.loads(target.read_text(encoding="utf-8"))
        return cls(
            server_url=str(data.get("server_url", cls.server_url)).rstrip("/"),
            poll_seconds=max(2, min(60, int(data.get("poll_seconds", 3)))),
            tls_fingerprint=str(data.get("tls_fingerprint", "")).upper(),
        )

    def save(self, path: Path | None = None) -> Path:
        target = path or default_client_config()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                {"server_url": self.server_url.rstrip("/"), "poll_seconds": self.poll_seconds,
                 "tls_fingerprint": self.tls_fingerprint},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return target


@dataclass(slots=True)
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 8765
    tls_mode: str = "auto"
    tls_cert: str = ""
    tls_key: str = ""
    backup_interval_hours: int = 24
    backup_retention: int = 30
    log_level: str = "INFO"

    @classmethod
    def load(cls, data_dir: Path) -> "ServerConfig":
        path = data_dir / "server.json"
        if not path.exists():
            config = cls()
            config.save(data_dir)
            return config
        data = json.loads(path.read_text(encoding="utf-8"))
        tls_mode = str(data.get("tls_mode", "auto"))
        if tls_mode not in {"auto", "custom", "off"}:
            raise ValueError("tls_mode must be auto, custom or off")
        return cls(
            host=str(data.get("host", "0.0.0.0")),
            port=max(1, min(65535, int(data.get("port", 8765)))),
            tls_mode=tls_mode,
            tls_cert=str(data.get("tls_cert", "")),
            tls_key=str(data.get("tls_key", "")),
            backup_interval_hours=max(1, min(168, int(data.get("backup_interval_hours", 24)))),
            backup_retention=max(3, min(365, int(data.get("backup_retention", 30)))),
            log_level=str(data.get("log_level", "INFO")).upper(),
        )

    def save(self, data_dir: Path) -> Path:
        data_dir.mkdir(parents=True, exist_ok=True)
        path = data_dir / "server.json"
        path.write_text(json.dumps({
            "host": self.host, "port": self.port, "tls_mode": self.tls_mode,
            "tls_cert": self.tls_cert, "tls_key": self.tls_key,
            "backup_interval_hours": self.backup_interval_hours,
            "backup_retention": self.backup_retention, "log_level": self.log_level,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        return path
