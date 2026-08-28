"""Central SQLite repository. Only the server process opens this database."""

from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import json
import secrets
import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterator

from .security import (
    SecretBox,
    audit_digest,
    generate_totp_secret,
    hash_bootstrap_password, hash_password,
    new_session_token,
    normalize_username,
    recovery_code,
    token_digest,
    verify_totp,
    verify_password,
)
from .migrations import apply_migrations
from .config import validate_database_identity

UTC = dt.timezone.utc
SESSION_HOURS = 10

SCHEMA = r"""
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS metadata (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  username TEXT NOT NULL UNIQUE COLLATE NOCASE,
  display_name TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('owner','admin','editor','viewer')),
  is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
  must_change_password INTEGER NOT NULL DEFAULT 1 CHECK(must_change_password IN (0,1)),
  failed_attempts INTEGER NOT NULL DEFAULT 0,
  locked_until TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  row_version INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE TABLE IF NOT EXISTS personnel (
  id TEXT PRIMARY KEY,
  personnel_no TEXT NOT NULL UNIQUE,
  first_name TEXT NOT NULL DEFAULT '',
  last_name TEXT NOT NULL DEFAULT '',
  full_name TEXT NOT NULL,
  gender TEXT NOT NULL DEFAULT '',
  organizational_unit TEXT NOT NULL DEFAULT '',
  position_code TEXT NOT NULL DEFAULT '',
  position_title TEXT NOT NULL DEFAULT '',
  employment_group TEXT NOT NULL DEFAULT '',
  employment_subtype TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT '',
  activity_area TEXT NOT NULL DEFAULT '',
  actual_location TEXT NOT NULL DEFAULT '',
  company TEXT NOT NULL DEFAULT '',
  chart_page_no INTEGER,
  chart_node_id TEXT NOT NULL DEFAULT '',
  extra_json TEXT NOT NULL DEFAULT '{}',
  row_version INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL,
  updated_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_personnel_name ON personnel(full_name);
CREATE INDEX IF NOT EXISTS idx_personnel_unit ON personnel(organizational_unit);
CREATE TABLE IF NOT EXISTS chart_pages (
  page_no INTEGER PRIMARY KEY,
  title TEXT NOT NULL,
  approved_fixed_posts INTEGER,
  approved_named_posts INTEGER,
  approved_total_posts INTEGER,
  extra_json TEXT NOT NULL DEFAULT '{}',
  row_version INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL,
  updated_by TEXT
);
CREATE TABLE IF NOT EXISTS chart_nodes (
  id TEXT NOT NULL,
  page_no INTEGER NOT NULL REFERENCES chart_pages(page_no) ON DELETE CASCADE,
  node_json TEXT NOT NULL,
  row_version INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL,
  updated_by TEXT,
  PRIMARY KEY(page_no, id)
);
CREATE TABLE IF NOT EXISTS chart_lines (
  id TEXT NOT NULL,
  page_no INTEGER NOT NULL REFERENCES chart_pages(page_no) ON DELETE CASCADE,
  line_json TEXT NOT NULL,
  row_version INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL,
  updated_by TEXT,
  PRIMARY KEY(page_no, id)
);
CREATE TABLE IF NOT EXISTS dashboard_widgets (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  widget_type TEXT NOT NULL,
  config_json TEXT NOT NULL DEFAULT '{}',
  position INTEGER NOT NULL,
  is_enabled INTEGER NOT NULL DEFAULT 1 CHECK(is_enabled IN (0,1)),
  row_version INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL,
  updated_by TEXT
);
CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  occurred_at TEXT NOT NULL,
  user_id TEXT,
  action TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  before_json TEXT,
  after_json TEXT,
  previous_hash TEXT NOT NULL,
  event_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS change_feed (
  revision INTEGER PRIMARY KEY AUTOINCREMENT,
  occurred_at TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  action TEXT NOT NULL,
  row_version INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS login_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  occurred_at TEXT NOT NULL,
  username TEXT NOT NULL,
  remote_address TEXT NOT NULL,
  succeeded INTEGER NOT NULL CHECK(succeeded IN (0,1))
);
"""

PERMISSION_DESCRIPTIONS = {
    "read": "مشاهده اطلاعات",
    "edit_personnel": "ایجاد و ویرایش پرسنل",
    "delete_personnel": "حذف پرسنل",
    "edit_chart": "ویرایش چارت سازمانی",
    "edit_dashboard": "ویرایش داشبورد",
    "view_audit": "مشاهده ممیزی",
    "manage_users": "مدیریت کاربران و ریزدسترسی",
    "backup": "تهیه پشتیبان",
    "restore": "بازیابی پشتیبان",
    "manage_workflows": "مدیریت گردش کار",
    "view_monitoring": "مشاهده پایش سامانه",
    "manage_security": "تنظیمات امنیت و MFA",
}

PERMISSIONS = {
    "owner": set(PERMISSION_DESCRIPTIONS),
    "admin": set(PERMISSION_DESCRIPTIONS) - {"restore"},
    "editor": {"read", "edit_personnel", "edit_chart", "edit_dashboard", "manage_workflows"},
    "viewer": {"read"},
}


def utc_now() -> str:
    return dt.datetime.now(UTC).isoformat(timespec="seconds")


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class ConflictError(RuntimeError):
    pass


class AuthenticationError(RuntimeError):
    pass


class MfaRequired(AuthenticationError):
    pass


class PermissionDenied(RuntimeError):
    pass


class ClosingConnection(sqlite3.Connection):
    """SQLite connection whose context manager also closes the file handle.

    sqlite3.Connection normally commits/rolls back on ``with`` exit but keeps
    the underlying database file open. Windows then refuses cleanup, restore,
    and replacement operations with WinError 32.
    """

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


class Repository:
    def __init__(self, path: Path):
        self.path = Path(path)
        validate_database_identity(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.RLock()
        self._secrets: SecretBox | None = None
        self.initialize()

    @property
    def secrets(self) -> SecretBox:
        if self._secrets is None:
            self._secrets = SecretBox(self.path.parent / "secrets.key")
        return self._secrets

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self.path,
            timeout=30,
            isolation_level=None,
            factory=ClosingConnection,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            apply_migrations(conn)
            for name, description in PERMISSION_DESCRIPTIONS.items():
                conn.execute("INSERT OR IGNORE INTO permissions(name,description) VALUES(?,?)", (name, description))
            for role, permissions in PERMISSIONS.items():
                for permission in permissions:
                    conn.execute("INSERT OR IGNORE INTO role_permissions(role,permission) VALUES(?,?)", (role, permission))

    @contextlib.contextmanager
    def write(self) -> Iterator[sqlite3.Connection]:
        with self._write_lock, self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except Exception:
                conn.rollback()
                raise
            else:
                conn.commit()

    def has_users(self) -> bool:
        with self.connect() as conn:
            return bool(conn.execute("SELECT 1 FROM users LIMIT 1").fetchone())

    def create_user(
        self,
        username: str,
        display_name: str,
        password: str,
        role: str,
        *,
        actor_id: str | None = None,
        must_change_password: bool = True,
        bootstrap_password: bool = False,
    ) -> dict[str, Any]:
        username = normalize_username(username)
        if role not in PERMISSIONS:
            raise ValueError("نقش کاربری معتبر نیست.")
        now = utc_now()
        user_id = secrets.token_hex(16)
        row = {
            "id": user_id,
            "username": username,
            "display_name": display_name.strip(),
            "role": role,
            "is_active": 1,
            "must_change_password": int(must_change_password),
            "created_at": now,
            "updated_at": now,
            "row_version": 1,
        }
        with self.write() as conn:
            conn.execute(
                """INSERT INTO users(id,username,display_name,password_hash,role,is_active,
                   must_change_password,created_at,updated_at,row_version)
                   VALUES(?,?,?,?,?,?,?,?,?,1)""",
                (user_id, username, row["display_name"],
                 hash_bootstrap_password(password) if bootstrap_password else hash_password(password), role, 1,
                 int(must_change_password), now, now),
            )
            self._record(conn, actor_id, "create", "user", user_id, None, row, 1)
        return row

    def authenticate(self, username: str, password: str, remote_address: str, otp: str = "") -> dict[str, Any]:
        try:
            username = normalize_username(username)
        except ValueError as exc:
            raise AuthenticationError("نام کاربری یا رمز عبور نادرست است.") from exc
        now_dt = dt.datetime.now(UTC)
        now = now_dt.isoformat(timespec="seconds")
        failure: str | None = None
        raw_token = expiry = ""
        public_user: dict[str, Any] = {}
        with self.write() as conn:
            row = conn.execute("SELECT * FROM users WHERE username=? COLLATE NOCASE", (username,)).fetchone()
            locked = False
            if row and row["locked_until"]:
                locked = dt.datetime.fromisoformat(row["locked_until"]) > now_dt
            password_ok = bool(row and row["is_active"] and not locked and verify_password(password, row["password_hash"]))
            mfa_row = conn.execute("SELECT * FROM mfa_totp WHERE user_id=? AND is_enabled=1", (row["id"],)).fetchone() if row else None
            mfa_ok = not mfa_row
            if mfa_row and otp:
                mfa_ok = verify_totp(self.secrets.decrypt(mfa_row["secret_encrypted"]), otp)
                if not mfa_ok:
                    recovery_hash = hashlib.sha256(otp.strip().upper().encode("ascii", "ignore")).hexdigest()
                    recovery = conn.execute("""SELECT 1 FROM mfa_recovery_codes
                        WHERE user_id=? AND code_hash=? AND used_at IS NULL""", (row["id"], recovery_hash)).fetchone()
                    if recovery:
                        conn.execute("UPDATE mfa_recovery_codes SET used_at=? WHERE user_id=? AND code_hash=?",
                                     (now, row["id"], recovery_hash))
                        mfa_ok = True
            success = bool(password_ok and mfa_ok)
            conn.execute(
                "INSERT INTO login_events(occurred_at,username,remote_address,succeeded) VALUES(?,?,?,?)",
                (now, username, remote_address[:128], int(success)),
            )
            if password_ok and mfa_row and not otp:
                failure = "mfa_required"
            elif not success:
                if row and not locked:
                    attempts = int(row["failed_attempts"]) + 1
                    locked_until = None
                    if attempts >= 5:
                        locked_until = (now_dt + dt.timedelta(minutes=15)).isoformat(timespec="seconds")
                        attempts = 0
                    conn.execute(
                        "UPDATE users SET failed_attempts=?,locked_until=?,updated_at=? WHERE id=?",
                        (attempts, locked_until, now, row["id"]),
                    )
                failure = "invalid"
            else:
                conn.execute("UPDATE users SET failed_attempts=0,locked_until=NULL,updated_at=? WHERE id=?", (now, row["id"]))
                raw_token, hashed_token = new_session_token()
                expiry = (now_dt + dt.timedelta(hours=SESSION_HOURS)).isoformat(timespec="seconds")
                conn.execute(
                    "INSERT INTO sessions(token_hash,user_id,created_at,expires_at,last_seen_at) VALUES(?,?,?,?,?)",
                    (hashed_token, row["id"], now, expiry, now),
                )
                public_user = self._public_user(dict(row))
        if failure == "mfa_required":
            raise MfaRequired("کد ورود دومرحله‌ای الزامی است.")
        if failure:
            raise AuthenticationError("نام کاربری یا رمز عبور نادرست است.")
        return {"token": raw_token, "expires_at": expiry, "user": public_user}

    def session_user(self, raw_token: str) -> dict[str, Any]:
        now_dt = dt.datetime.now(UTC)
        with self.connect() as conn:
            row = conn.execute(
                """SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id
                   WHERE s.token_hash=? AND u.is_active=1""",
                (token_digest(raw_token),),
            ).fetchone()
            if not row:
                raise AuthenticationError("نشست معتبر نیست.")
            if dt.datetime.fromisoformat(conn.execute(
                "SELECT expires_at FROM sessions WHERE token_hash=?", (token_digest(raw_token),)
            ).fetchone()[0]) <= now_dt:
                conn.execute("DELETE FROM sessions WHERE token_hash=?", (token_digest(raw_token),))
                raise AuthenticationError("نشست منقضی شده است.")
            conn.execute(
                "UPDATE sessions SET last_seen_at=? WHERE token_hash=?",
                (now_dt.isoformat(timespec="seconds"), token_digest(raw_token)),
            )
            return self._public_user(dict(row))

    def logout(self, raw_token: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash=?", (token_digest(raw_token),))

    def change_password(self, user_id: str, current: str, new_password: str) -> None:
        remove_initial_notice = False
        with self.write() as conn:
            row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            if not row or not verify_password(current, row["password_hash"]):
                raise AuthenticationError("رمز عبور فعلی نادرست است.")
            conn.execute(
                "UPDATE users SET password_hash=?,must_change_password=0,updated_at=?,row_version=row_version+1 WHERE id=?",
                (hash_password(new_password), utc_now(), user_id),
            )
            self._record(conn, user_id, "change_password", "user", user_id, None, {"changed": True}, int(row["row_version"]) + 1)
            initial_owner = conn.execute("SELECT value FROM metadata WHERE key='initial_owner_id'").fetchone()
            remove_initial_notice = bool(initial_owner and initial_owner[0] == user_id)
        if remove_initial_notice:
            (self.path.parent / "FIRST_LOGIN.txt").unlink(missing_ok=True)

    def list_users(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT id,username,display_name,role,is_active,must_change_password,created_at,
                   updated_at,row_version FROM users ORDER BY display_name,username"""
            ).fetchall()
        return [dict(row) for row in rows]

    def mfa_status(self, user_id: str) -> dict[str, bool]:
        with self.connect() as conn:
            row = conn.execute("SELECT is_enabled FROM mfa_totp WHERE user_id=?", (user_id,)).fetchone()
        return {"configured": bool(row), "enabled": bool(row and row[0])}

    @staticmethod
    def _public_user(row: dict[str, Any]) -> dict[str, Any]:
        return {key: row[key] for key in (
            "id", "username", "display_name", "role", "is_active", "must_change_password", "row_version"
        ) if key in row}

    def permissions_for(self, user: dict[str, Any]) -> set[str]:
        with self.connect() as conn:
            base = {row[0] for row in conn.execute("SELECT permission FROM role_permissions WHERE role=?", (user.get("role", ""),))}
            overrides = conn.execute("SELECT permission,effect FROM user_permissions WHERE user_id=?", (user["id"],)).fetchall()
        for row in overrides:
            if row["effect"] == "allow":
                base.add(row["permission"])
            else:
                base.discard(row["permission"])
        return base

    def require(self, user: dict[str, Any], permission: str) -> None:
        if permission not in self.permissions_for(user):
            raise PermissionDenied("دسترسی لازم برای این عملیات وجود ندارد.")

    def set_user_permissions(self, target_user_id: str, overrides: dict[str, str], actor_id: str) -> dict[str, Any]:
        invalid = {key: value for key, value in overrides.items()
                   if key not in PERMISSION_DESCRIPTIONS or value not in {"allow", "deny"}}
        if invalid:
            raise ValueError("ریز‌دسترسی نامعتبر است.")
        with self.write() as conn:
            if not conn.execute("SELECT 1 FROM users WHERE id=?", (target_user_id,)).fetchone():
                raise ValueError("کاربر پیدا نشد.")
            conn.execute("DELETE FROM user_permissions WHERE user_id=?", (target_user_id,))
            for permission, effect in overrides.items():
                conn.execute("INSERT INTO user_permissions(user_id,permission,effect) VALUES(?,?,?)",
                             (target_user_id, permission, effect))
            self._record(conn, actor_id, "set_permissions", "user", target_user_id, None, overrides, 1)
        return {"user_id": target_user_id, "overrides": overrides}

    def begin_mfa(self, user_id: str, username: str, current_password: str) -> dict[str, str]:
        secret = generate_totp_secret()
        with self.write() as conn:
            user = conn.execute("SELECT password_hash FROM users WHERE id=?", (user_id,)).fetchone()
            if not user or not verify_password(current_password, user[0]):
                raise AuthenticationError("برای تغییر MFA، رمز عبور فعلی لازم است.")
            conn.execute("""INSERT OR REPLACE INTO mfa_totp(user_id,secret_encrypted,is_enabled,created_at,confirmed_at)
                VALUES(?,?,0,?,NULL)""", (user_id, self.secrets.encrypt(secret), utc_now()))
        uri = f"otpauth://totp/HRM:{username}?secret={secret}&issuer=HRM&digits=6&period=30"
        return {"secret": secret, "otpauth_uri": uri}

    def confirm_mfa(self, user_id: str, code: str) -> list[str]:
        with self.write() as conn:
            row = conn.execute("SELECT secret_encrypted FROM mfa_totp WHERE user_id=?", (user_id,)).fetchone()
            if not row or not verify_totp(self.secrets.decrypt(row[0]), code):
                raise AuthenticationError("کد ورود دومرحله‌ای معتبر نیست.")
            codes = [recovery_code() for _ in range(8)]
            conn.execute("DELETE FROM mfa_recovery_codes WHERE user_id=?", (user_id,))
            for code_value in codes:
                conn.execute("INSERT INTO mfa_recovery_codes(user_id,code_hash) VALUES(?,?)",
                             (user_id, hashlib.sha256(code_value.encode("ascii")).hexdigest()))
            conn.execute("UPDATE mfa_totp SET is_enabled=1,confirmed_at=? WHERE user_id=?", (utc_now(), user_id))
            self._record(conn, user_id, "enable_mfa", "user", user_id, None, {"enabled": True}, 1)
        return codes

    def stats(self) -> dict[str, int]:
        with self.connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM personnel").fetchone()[0]
            active = conn.execute("SELECT COUNT(*) FROM personnel WHERE status NOT LIKE '%غیرفعال%'").fetchone()[0]
            units = conn.execute(
                "SELECT COUNT(DISTINCT organizational_unit) FROM personnel WHERE organizational_unit<>''"
            ).fetchone()[0]
            unassigned = conn.execute(
                "SELECT COUNT(*) FROM personnel WHERE position_code='' OR position_title=''"
            ).fetchone()[0]
            revision = conn.execute("SELECT COALESCE(MAX(revision),0) FROM change_feed").fetchone()[0]
        return {"personnel": total, "active": active, "units": units, "unassigned": unassigned, "revision": revision}

    def list_personnel(self, query: str = "", limit: int = 200, offset: int = 0) -> dict[str, Any]:
        limit = max(1, min(limit, 1000))
        offset = max(0, offset)
        like = f"%{query.strip()}%"
        where = "" if not query.strip() else "WHERE personnel_no LIKE ? OR full_name LIKE ? OR organizational_unit LIKE ? OR position_title LIKE ?"
        params: tuple[Any, ...] = () if not where else (like, like, like, like)
        with self.connect() as conn:
            total = conn.execute(f"SELECT COUNT(*) FROM personnel {where}", params).fetchone()[0]
            rows = conn.execute(
                f"""SELECT id,personnel_no,first_name,last_name,full_name,gender,organizational_unit,
                    position_code,position_title,employment_group,employment_subtype,status,
                    activity_area,actual_location,company,chart_page_no,chart_node_id,row_version,updated_at
                    FROM personnel {where} ORDER BY full_name,personnel_no LIMIT ? OFFSET ?""",
                (*params, limit, offset),
            ).fetchall()
        return {"items": [dict(row) for row in rows], "total": total, "limit": limit, "offset": offset}

    def get_person(self, person_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM personnel WHERE id=?", (person_id,)).fetchone()
        if not row:
            return None
        result = dict(row)
        result["extra"] = json.loads(result.pop("extra_json") or "{}")
        return result

    def save_person(self, payload: dict[str, Any], actor_id: str) -> dict[str, Any]:
        person_id = str(payload.get("id") or secrets.token_hex(16))
        now = utc_now()
        fields = (
            "personnel_no", "first_name", "last_name", "full_name", "gender", "organizational_unit",
            "position_code", "position_title", "employment_group", "employment_subtype", "status",
            "activity_area", "actual_location", "company", "chart_node_id",
        )
        values = {field: str(payload.get(field, "")).strip() for field in fields}
        chart_page_text = str(payload.get("chart_page_no", "")).strip()
        chart_page_no = int(chart_page_text) if chart_page_text else None
        if not values["personnel_no"] or not values["full_name"]:
            raise ValueError("شماره پرسنلی و نام کامل الزامی است.")
        with self.write() as conn:
            old_row = conn.execute("SELECT * FROM personnel WHERE id=?", (person_id,)).fetchone()
            if old_row:
                expected = int(payload.get("row_version", 0))
                if expected != int(old_row["row_version"]):
                    raise ConflictError("این رکورد هم‌زمان توسط مدیر دیگری تغییر کرده است؛ فهرست را تازه‌سازی کنید.")
                new_version = expected + 1
                conn.execute(
                    """UPDATE personnel SET personnel_no=?,first_name=?,last_name=?,full_name=?,gender=?,
                    organizational_unit=?,position_code=?,position_title=?,employment_group=?,employment_subtype=?,
                    status=?,activity_area=?,actual_location=?,company=?,chart_node_id=?,chart_page_no=?,extra_json=?,row_version=?,updated_at=?,updated_by=?
                    WHERE id=? AND row_version=?""",
                    tuple(values[f] for f in fields) + (chart_page_no, canonical(payload.get("extra", {})), new_version, now, actor_id, person_id, expected),
                )
                action = "update"
                before = dict(old_row)
            else:
                new_version = 1
                conn.execute(
                    """INSERT INTO personnel(id,personnel_no,first_name,last_name,full_name,gender,
                    organizational_unit,position_code,position_title,employment_group,employment_subtype,status,
                    activity_area,actual_location,company,chart_node_id,chart_page_no,extra_json,row_version,updated_at,updated_by)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (person_id,) + tuple(values[f] for f in fields) + (chart_page_no, canonical(payload.get("extra", {})), 1, now, actor_id),
                )
                action = "create"
                before = None
            after = {"id": person_id, **values, "chart_page_no": chart_page_no,
                     "row_version": new_version, "updated_at": now}
            self._record(conn, actor_id, action, "personnel", person_id, before, after, new_version)
        return self.get_person(person_id) or after

    def delete_person(self, person_id: str, expected_version: int, actor_id: str) -> None:
        with self.write() as conn:
            row = conn.execute("SELECT * FROM personnel WHERE id=?", (person_id,)).fetchone()
            if not row:
                return
            if int(row["row_version"]) != int(expected_version):
                raise ConflictError("رکورد تغییر کرده است؛ حذف انجام نشد.")
            conn.execute("DELETE FROM personnel WHERE id=?", (person_id,))
            self._record(conn, actor_id, "delete", "personnel", person_id, dict(row), None, expected_version + 1)

    def list_widgets(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM dashboard_widgets ORDER BY position,id").fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["config"] = json.loads(item.pop("config_json") or "{}")
            result.append(item)
        return result

    def save_widget(self, payload: dict[str, Any], actor_id: str) -> dict[str, Any]:
        widget_id = str(payload.get("id") or secrets.token_hex(10))
        title = str(payload.get("title", "")).strip()
        widget_type = str(payload.get("widget_type", "number")).strip()
        if not title or widget_type not in {"number", "text", "shortcut"}:
            raise ValueError("عنوان یا نوع ویجت معتبر نیست.")
        with self.write() as conn:
            old = conn.execute("SELECT * FROM dashboard_widgets WHERE id=?", (widget_id,)).fetchone()
            now = utc_now()
            if old:
                expected = int(payload.get("row_version", 0))
                if expected != int(old["row_version"]):
                    raise ConflictError("ویجت توسط مدیر دیگری تغییر کرده است.")
                version = expected + 1
                conn.execute(
                    """UPDATE dashboard_widgets SET title=?,widget_type=?,config_json=?,position=?,is_enabled=?,
                    row_version=?,updated_at=?,updated_by=? WHERE id=? AND row_version=?""",
                    (title, widget_type, canonical(payload.get("config", {})), int(payload.get("position", 0)),
                     int(bool(payload.get("is_enabled", True))), version, now, actor_id, widget_id, expected),
                )
                before, action = dict(old), "update"
            else:
                version = 1
                conn.execute(
                    """INSERT INTO dashboard_widgets(id,title,widget_type,config_json,position,is_enabled,row_version,updated_at,updated_by)
                    VALUES(?,?,?,?,?,?,?,?,?)""",
                    (widget_id, title, widget_type, canonical(payload.get("config", {})), int(payload.get("position", 0)),
                     int(bool(payload.get("is_enabled", True))), 1, now, actor_id),
                )
                before, action = None, "create"
            after = {"id": widget_id, "title": title, "widget_type": widget_type,
                     "config": payload.get("config", {}), "position": int(payload.get("position", 0)),
                     "is_enabled": int(bool(payload.get("is_enabled", True))), "row_version": version, "updated_at": now}
            self._record(conn, actor_id, action, "dashboard_widget", widget_id, before, after, version)
        return after

    def delete_widget(self, widget_id: str, expected_version: int, actor_id: str) -> None:
        with self.write() as conn:
            row = conn.execute("SELECT * FROM dashboard_widgets WHERE id=?", (widget_id,)).fetchone()
            if not row:
                return
            if int(row["row_version"]) != int(expected_version):
                raise ConflictError("ویجت تغییر کرده است؛ حذف انجام نشد.")
            conn.execute("DELETE FROM dashboard_widgets WHERE id=?", (widget_id,))
            self._record(conn, actor_id, "delete", "dashboard_widget", widget_id, dict(row), None, expected_version + 1)

    def list_chart_pages(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT page_no,title,approved_fixed_posts,approved_named_posts,approved_total_posts,row_version FROM chart_pages ORDER BY page_no"
            ).fetchall()
        return [dict(row) for row in rows]

    def get_chart_page(self, page_no: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            page = conn.execute("SELECT * FROM chart_pages WHERE page_no=?", (page_no,)).fetchone()
            if not page:
                return None
            nodes = conn.execute("SELECT node_json FROM chart_nodes WHERE page_no=? ORDER BY id", (page_no,)).fetchall()
            lines = conn.execute("SELECT line_json FROM chart_lines WHERE page_no=? ORDER BY id", (page_no,)).fetchall()
        result = dict(page)
        result["extra"] = json.loads(result.pop("extra_json") or "{}")
        result["nodes"] = [json.loads(row[0]) for row in nodes]
        result["lines"] = [json.loads(row[0]) for row in lines]
        return result

    def save_chart_page(self, page_no: int, payload: dict[str, Any], actor_id: str) -> dict[str, Any]:
        if page_no < 1:
            raise ValueError("شماره صفحه معتبر نیست.")
        title = str(payload.get("title", "")).strip()
        if not title:
            raise ValueError("عنوان صفحه الزامی است.")
        nodes = payload.get("nodes", [])
        lines = payload.get("lines", [])
        if not isinstance(nodes, list) or not isinstance(lines, list):
            raise ValueError("ساختار گره‌ها یا خطوط معتبر نیست.")
        now = utc_now()
        with self.write() as conn:
            old_page = conn.execute("SELECT * FROM chart_pages WHERE page_no=?", (page_no,)).fetchone()
            before = self.get_chart_page(page_no) if old_page else None
            if old_page:
                expected = int(payload.get("row_version", 0))
                if expected != int(old_page["row_version"]):
                    raise ConflictError("این صفحه چارت توسط مدیر دیگری تغییر کرده است.")
                version = expected + 1
                conn.execute(
                    """UPDATE chart_pages SET title=?,approved_fixed_posts=?,approved_named_posts=?,
                    approved_total_posts=?,extra_json=?,row_version=?,updated_at=?,updated_by=?
                    WHERE page_no=? AND row_version=?""",
                    (title, payload.get("approved_fixed_posts"), payload.get("approved_named_posts"),
                     payload.get("approved_total_posts"), canonical(payload.get("extra", {})), version,
                     now, actor_id, page_no, expected),
                )
                conn.execute("DELETE FROM chart_nodes WHERE page_no=?", (page_no,))
                conn.execute("DELETE FROM chart_lines WHERE page_no=?", (page_no,))
                action = "update"
            else:
                version = 1
                conn.execute(
                    """INSERT INTO chart_pages(page_no,title,approved_fixed_posts,approved_named_posts,
                    approved_total_posts,extra_json,row_version,updated_at,updated_by) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (page_no, title, payload.get("approved_fixed_posts"), payload.get("approved_named_posts"),
                     payload.get("approved_total_posts"), canonical(payload.get("extra", {})), 1, now, actor_id),
                )
                action = "create"
            for index, node in enumerate(nodes):
                node_id = str(node.get("id") or node.get("node_id") or f"node-{index + 1}")
                conn.execute(
                    "INSERT INTO chart_nodes(id,page_no,node_json,row_version,updated_at,updated_by) VALUES(?,?,?,?,?,?)",
                    (node_id, page_no, canonical(node), 1, now, actor_id),
                )
            for index, line in enumerate(lines):
                line_id = str(line.get("id") or f"line-{index + 1}")
                conn.execute(
                    "INSERT INTO chart_lines(id,page_no,line_json,row_version,updated_at,updated_by) VALUES(?,?,?,?,?,?)",
                    (line_id, page_no, canonical(line), 1, now, actor_id),
                )
            after = {"page_no": page_no, "title": title, "nodes": nodes, "lines": lines,
                     "row_version": version, "updated_at": now}
            self._record(conn, actor_id, action, "chart_page", str(page_no), before, after, version)
        return self.get_chart_page(page_no) or after

    def changes(self, since: int, limit: int = 500) -> dict[str, Any]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM change_feed WHERE revision>? ORDER BY revision LIMIT ?", (max(0, since), min(limit, 1000))
            ).fetchall()
            current = conn.execute("SELECT COALESCE(MAX(revision),0) FROM change_feed").fetchone()[0]
        return {"items": [dict(row) for row in rows], "current_revision": current}

    def audit(self, limit: int = 200) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT a.id,a.occurred_at,u.username,a.action,a.entity_type,a.entity_id,a.event_hash
                   FROM audit_log a LEFT JOIN users u ON u.id=a.user_id ORDER BY a.id DESC LIMIT ?""",
                (min(max(limit, 1), 1000),),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_workflow(self, payload: dict[str, Any], actor_id: str) -> dict[str, Any]:
        workflow_id = secrets.token_hex(16)
        now = utc_now()
        item = {
            "id": workflow_id,
            "workflow_type": str(payload.get("workflow_type", "general")).strip(),
            "title": str(payload.get("title", "")).strip(),
            "entity_type": str(payload.get("entity_type", "personnel")).strip(),
            "entity_id": str(payload.get("entity_id", "")).strip(),
            "state": "pending",
            "payload": payload.get("payload", {}),
            "assigned_to": payload.get("assigned_to") or None,
            "due_at": payload.get("due_at") or None,
            "created_by": actor_id,
            "created_at": now,
            "updated_at": now,
            "row_version": 1,
        }
        if not item["title"] or not item["entity_id"]:
            raise ValueError("عنوان و شناسه موضوع گردش کار الزامی است.")
        with self.write() as conn:
            conn.execute("""INSERT INTO workflows(id,workflow_type,title,entity_type,entity_id,state,payload_json,
                assigned_to,due_at,created_by,created_at,updated_at,row_version) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,1)""",
                (workflow_id, item["workflow_type"], item["title"], item["entity_type"], item["entity_id"],
                 item["state"], canonical(item["payload"]), item["assigned_to"], item["due_at"], actor_id, now, now))
            conn.execute("""INSERT INTO workflow_events(workflow_id,action,from_state,to_state,note,actor_id,occurred_at)
                VALUES(?, 'create', NULL, 'pending', ?, ?, ?)""",
                (workflow_id, str(payload.get("note", "")), actor_id, now))
            if item["assigned_to"]:
                self._insert_notification(conn, item["assigned_to"], "info", "گردش کار جدید",
                                          item["title"], "workflow", workflow_id)
            self._record(conn, actor_id, "create", "workflow", workflow_id, None, item, 1)
        return item

    def list_workflows(self, state: str = "", limit: int = 300) -> list[dict[str, Any]]:
        where, params = ("", ()) if not state else ("WHERE w.state=?", (state,))
        with self.connect() as conn:
            rows = conn.execute(f"""SELECT w.*,u.display_name AS assigned_name FROM workflows w
                LEFT JOIN users u ON u.id=w.assigned_to {where} ORDER BY w.updated_at DESC LIMIT ?""",
                (*params, min(max(limit, 1), 1000))).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item.pop("payload_json") or "{}")
            result.append(item)
        return result

    def transition_workflow(self, workflow_id: str, to_state: str, note: str, actor_id: str,
                            expected_version: int) -> dict[str, Any]:
        transitions = {
            "pending": {"in_progress", "approved", "rejected", "cancelled"},
            "in_progress": {"approved", "rejected", "cancelled"},
            "approved": set(), "rejected": set(), "cancelled": set(),
        }
        with self.write() as conn:
            row = conn.execute("SELECT * FROM workflows WHERE id=?", (workflow_id,)).fetchone()
            if not row:
                raise ValueError("گردش کار پیدا نشد.")
            if int(row["row_version"]) != expected_version:
                raise ConflictError("گردش کار توسط مدیر دیگری تغییر کرده است.")
            if to_state not in transitions.get(row["state"], set()):
                raise ValueError("این انتقال وضعیت مجاز نیست.")
            now, version = utc_now(), expected_version + 1
            conn.execute("UPDATE workflows SET state=?,updated_at=?,row_version=? WHERE id=? AND row_version=?",
                         (to_state, now, version, workflow_id, expected_version))
            conn.execute("""INSERT INTO workflow_events(workflow_id,action,from_state,to_state,note,actor_id,occurred_at)
                VALUES(?,'transition',?,?,?,?,?)""", (workflow_id, row["state"], to_state, note, actor_id, now))
            if row["assigned_to"]:
                self._insert_notification(conn, row["assigned_to"], "info", "وضعیت گردش کار تغییر کرد",
                                          f"{row['title']} ← {to_state}", "workflow", workflow_id)
            after = {**dict(row), "state": to_state, "updated_at": now, "row_version": version}
            self._record(conn, actor_id, "transition", "workflow", workflow_id, dict(row), after, version)
        return after

    def notifications(self, user_id: str, unread_only: bool = False, limit: int = 200) -> list[dict[str, Any]]:
        where = "AND is_read=0" if unread_only else ""
        with self.connect() as conn:
            rows = conn.execute(f"""SELECT * FROM notifications
                WHERE (user_id=? OR user_id IS NULL) {where} ORDER BY created_at DESC LIMIT ?""",
                (user_id, min(max(limit, 1), 1000))).fetchall()
        return [dict(row) for row in rows]

    def mark_notification_read(self, notification_id: str, user_id: str) -> None:
        with self.write() as conn:
            conn.execute("""UPDATE notifications SET is_read=1,read_at=?
                WHERE id=? AND (user_id=? OR user_id IS NULL)""", (utc_now(), notification_id, user_id))

    def _insert_notification(self, conn: sqlite3.Connection, user_id: str | None, severity: str,
                             title: str, message: str, related_type: str | None = None,
                             related_id: str | None = None) -> str:
        notification_id = secrets.token_hex(16)
        conn.execute("""INSERT INTO notifications(id,user_id,severity,title,message,related_type,related_id,created_at)
            VALUES(?,?,?,?,?,?,?,?)""", (notification_id, user_id, severity, title, message,
                                           related_type, related_id, utc_now()))
        return notification_id

    def record_operational(self, level: str, component: str, event_code: str,
                           message: str, details: dict[str, Any] | None = None) -> None:
        with self.connect() as conn:
            conn.execute("""INSERT INTO operational_events(occurred_at,level,component,event_code,message,details_json)
                VALUES(?,?,?,?,?,?)""", (utc_now(), level, component, event_code, message, canonical(details or {})))

    def operational_events(self, limit: int = 200) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM operational_events ORDER BY id DESC LIMIT ?",
                                (min(max(limit, 1), 1000),)).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["details"] = json.loads(item.pop("details_json") or "{}")
            result.append(item)
        return result

    def monitoring(self) -> dict[str, Any]:
        with self.connect() as conn:
            db_size = self.path.stat().st_size if self.path.exists() else 0
            active_sessions = conn.execute("SELECT COUNT(*) FROM sessions WHERE expires_at>?", (utc_now(),)).fetchone()[0]
            unread = conn.execute("SELECT COUNT(*) FROM notifications WHERE is_read=0").fetchone()[0]
            pending = conn.execute("SELECT COUNT(*) FROM workflows WHERE state IN ('pending','in_progress')").fetchone()[0]
            last_backup = conn.execute("SELECT created_at,filename,integrity_ok FROM backup_catalog ORDER BY id DESC LIMIT 1").fetchone()
            schema_version = conn.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()[0]
        return {
            "database_size_bytes": db_size,
            "active_sessions": active_sessions,
            "unread_notifications": unread,
            "pending_workflows": pending,
            "audit_chain_valid": self.verify_audit_chain(),
            "schema_version": int(schema_version),
            "last_backup": dict(last_backup) if last_backup else None,
        }

    def verify_audit_chain(self) -> bool:
        previous = "0" * 64
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM audit_log ORDER BY id").fetchall()
        for row in rows:
            event = {
                "occurred_at": row["occurred_at"], "user_id": row["user_id"], "action": row["action"],
                "entity_type": row["entity_type"], "entity_id": row["entity_id"],
                "before_json": row["before_json"], "after_json": row["after_json"],
            }
            if row["previous_hash"] != previous or audit_digest(previous, canonical(event)) != row["event_hash"]:
                return False
            previous = row["event_hash"]
        return True

    def backup(self, destination: Path, created_by: str | None = None, kind: str = "manual") -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as source, contextlib.closing(sqlite3.connect(destination)) as target:
            source.backup(target)
        with contextlib.closing(sqlite3.connect(destination)) as check:
            integrity_ok = check.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        if not integrity_ok:
            destination.unlink(missing_ok=True)
            raise RuntimeError("نسخه پشتیبان آزمون سلامت را رد کرد.")
        digest = hashlib.sha256(destination.read_bytes()).hexdigest()
        with self.connect() as conn:
            conn.execute("""INSERT OR REPLACE INTO backup_catalog(created_at,filename,sha256,size_bytes,
                integrity_ok,created_by,kind) VALUES(?,?,?,?,1,?,?)""",
                (utc_now(), destination.name, digest, destination.stat().st_size, created_by, kind))
        return destination

    def list_backups(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM backup_catalog ORDER BY id DESC").fetchall()
        return [dict(row) for row in rows]

    def prune_backups(self, backup_dir: Path, keep: int = 30) -> int:
        keep = max(3, min(keep, 365))
        with self.write() as conn:
            rows = conn.execute("SELECT id,filename FROM backup_catalog ORDER BY id DESC").fetchall()
            removed = 0
            for row in rows[keep:]:
                (backup_dir / row["filename"]).unlink(missing_ok=True)
                conn.execute("DELETE FROM backup_catalog WHERE id=?", (row["id"],))
                removed += 1
        return removed

    def _record(
        self, conn: sqlite3.Connection, user_id: str | None, action: str, entity_type: str,
        entity_id: str, before: Any, after: Any, row_version: int,
    ) -> None:
        now = utc_now()
        previous_row = conn.execute("SELECT event_hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
        previous = previous_row[0] if previous_row else "0" * 64
        before_json = canonical(before) if before is not None else None
        after_json = canonical(after) if after is not None else None
        event = {
            "occurred_at": now, "user_id": user_id, "action": action, "entity_type": entity_type,
            "entity_id": entity_id, "before_json": before_json, "after_json": after_json,
        }
        digest = audit_digest(previous, canonical(event))
        conn.execute(
            """INSERT INTO audit_log(occurred_at,user_id,action,entity_type,entity_id,before_json,after_json,previous_hash,event_hash)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (now, user_id, action, entity_type, entity_id, before_json, after_json, previous, digest),
        )
        conn.execute(
            "INSERT INTO change_feed(occurred_at,entity_type,entity_id,action,row_version) VALUES(?,?,?,?,?)",
            (now, entity_type, entity_id, action, row_version),
        )
