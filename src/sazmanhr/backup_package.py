"""Portable binary backup envelope for the central Enterprise service.

Only the SQLite database is required for complete HRM state recovery: users,
permissions, personnel, organization projections, movement history, audit chain,
compatibility datasets and operational metadata all live in that database.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import sqlite3
import zipfile
from pathlib import Path
from typing import Any

from . import __version__
from .database import Repository, utc_now
from .config import validate_database_identity
from .operations import sqlite_integrity

BACKUP_FORMAT = "sazmanhr-enterprise-backup-v1"
MAX_RESTORE_BYTES = 512 * 1024 * 1024


def _db_counts(path: Path) -> tuple[int, int]:
    # sqlite3.Connection.__exit__ commits/rolls back but does *not* close the
    # underlying file handle.  That is observable on Windows where temporary
    # backup files cannot be deleted while this read-only connection remains
    # open (WinError 32).  Explicitly close it on every platform.
    with contextlib.closing(
        sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    ) as conn:
        people = int(conn.execute("SELECT COUNT(*) FROM personnel").fetchone()[0])
        slides = int(conn.execute("SELECT COUNT(*) FROM chart_pages").fetchone()[0])
    return people, slides


def create_package(repo: Repository, actor_id: str | None = None) -> tuple[bytes, dict[str, Any]]:
    backup_dir = repo.path.parent / "backups"
    stamp = utc_now().replace(":", "").replace("-", "").replace("+00:00", "Z")
    sqlite_name = f"manual-{stamp}.sqlite"
    sqlite_path = repo.backup(backup_dir / sqlite_name, actor_id, "manual-download")
    raw_db = sqlite_path.read_bytes()
    digest = hashlib.sha256(raw_db).hexdigest()
    people, slides = _db_counts(sqlite_path)
    manifest = {
        "format": BACKUP_FORMAT,
        "app_version": __version__,
        "created_at": utc_now(),
        "database_file": "database.sqlite",
        "database_sha256": digest,
        "database_size": len(raw_db),
        "people": people,
        "slides": slides,
    }
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, separators=(",", ":")))
        zf.writestr("database.sqlite", raw_db)
    package = out.getvalue()
    manifest["package_sha256"] = hashlib.sha256(package).hexdigest()
    manifest["package_size"] = len(package)
    manifest["filename"] = f"SazmanHR-Backup-{stamp}.sazhr.zip"
    return package, manifest


def inspect_package(raw: bytes) -> tuple[dict[str, Any], bytes]:
    if len(raw) < 500:
        raise ValueError("فایل پشتیبان بسیار کوچک یا نامعتبر است.")
    if len(raw) > MAX_RESTORE_BYTES:
        raise ValueError("حجم فایل پشتیبان بیش از حد مجاز است.")
    try:
        with zipfile.ZipFile(io.BytesIO(raw), "r") as zf:
            names = set(zf.namelist())
            if names != {"manifest.json", "database.sqlite"}:
                raise ValueError("ساختار فایل پشتیبان معتبر نیست.")
            info = zf.getinfo("database.sqlite")
            if info.file_size > MAX_RESTORE_BYTES:
                raise ValueError("حجم پایگاه داده پشتیبان بیش از حد مجاز است.")
            manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
            db_raw = zf.read("database.sqlite")
    except (zipfile.BadZipFile, KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("فایل پشتیبان معتبر نیست.") from exc
    if not isinstance(manifest, dict) or manifest.get("format") != BACKUP_FORMAT:
        raise ValueError("نسخه/قالب پشتیبان مورد تأیید نیست.")
    expected = str(manifest.get("database_sha256", ""))
    actual = hashlib.sha256(db_raw).hexdigest()
    if not expected or expected != actual:
        raise ValueError("هش پایگاه داده داخل پشتیبان معتبر نیست.")
    if int(manifest.get("database_size") or -1) != len(db_raw):
        raise ValueError("اندازه پایگاه داده داخل پشتیبان معتبر نیست.")
    return manifest, db_raw


def stage_database(raw: bytes, target: Path) -> dict[str, Any]:
    manifest, db_raw = inspect_package(raw)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(db_raw)
    ok, detail = sqlite_integrity(target)
    if not ok:
        target.unlink(missing_ok=True)
        raise ValueError(f"پایگاه داده پشتیبان آزمون سلامت را رد کرد: {detail}")
    try:
        validate_database_identity(target)
    except Exception as exc:
        target.unlink(missing_ok=True)
        raise ValueError("فایل ZIP شامل پایگاه داده HRM معتبر نیست.") from exc
    people, slides = _db_counts(target)
    if int(manifest.get("people") or -1) != people or int(manifest.get("slides") or -1) != slides:
        target.unlink(missing_ok=True)
        raise ValueError("شمارش‌های مانیفست پشتیبان با پایگاه داده سازگار نیست.")
    return {**manifest, "people": people, "slides": slides}
