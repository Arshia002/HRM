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
    "manage_movements": "ثبت جابه‌جایی‌های پرسنلی",
    "reverse_movements": "ابطال آخرین جابه‌جایی پرسنلی",
    "view_monitoring": "مشاهده پایش سامانه",
    "manage_security": "تنظیمات امنیت و MFA",
}

PERMISSIONS = {
    # owner = Super Admin: security, users, restore and destructive operations.
    "owner": set(PERMISSION_DESCRIPTIONS),
    # admin = HR Admin: full daily HR work without security/restore/hard-delete powers.
    "admin": {"read", "edit_personnel", "edit_dashboard", "view_audit", "backup",
              "manage_workflows", "manage_movements", "view_monitoring"},
    "editor": {"read", "edit_personnel", "manage_workflows", "manage_movements"},
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
            self._ensure_organization_projection(conn)

    @staticmethod
    def _projection_id(prefix: str, value: str) -> str:
        digest = hashlib.sha256(value.strip().encode("utf-8")).hexdigest()[:20]
        return f"{prefix}-{digest}"

    def _ensure_organization_projection(self, conn: sqlite3.Connection) -> None:
        """Backfill the normalized organization core from legacy personnel fields.

        v0.3.0-alpha.1 stored unit/position labels directly on personnel.  The
        alpha.2 core keeps those fields for backwards compatibility but adds a
        normalized projection for organization browsing, positions and profile
        assignment.  The projection is deterministic and idempotent, so an
        in-place upgrade preserves every existing personnel row.
        """
        now = utc_now()
        rows = conn.execute(
            """SELECT id,organizational_unit,position_code,position_title,actual_location
               FROM personnel ORDER BY personnel_no,id"""
        ).fetchall()
        for row in rows:
            unit_title = str(row["organizational_unit"] or "").strip()
            unit_id = None
            if unit_title:
                unit_id = self._projection_id("unit", unit_title)
                unit_code = "U-" + hashlib.sha256(unit_title.encode("utf-8")).hexdigest()[:8].upper()
                conn.execute(
                    """INSERT OR IGNORE INTO organizational_units
                       (id,code,title,parent_id,unit_type,location,is_active,sort_order,row_version,updated_at,updated_by)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (unit_id, unit_code, unit_title, None, "واحد سازمانی", str(row["actual_location"] or ""),
                     1, 0, 1, now, None),
                )
            position_code = str(row["position_code"] or "").strip()
            position_title = str(row["position_title"] or "").strip()
            if not position_code and not position_title:
                continue
            stable_position = position_code or f"{unit_title}|{position_title}"
            position_id = self._projection_id("position", stable_position)
            stored_code = position_code or ("P-" + hashlib.sha256(stable_position.encode("utf-8")).hexdigest()[:8].upper())
            conn.execute(
                """INSERT OR IGNORE INTO positions
                   (id,code,title,unit_id,post_type,location,status,row_version,updated_at,updated_by)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (position_id, stored_code, position_title or stored_code, unit_id, "",
                 str(row["actual_location"] or ""), "active", 1, now, None),
            )
            assignment_id = self._projection_id("assignment", str(row["id"]))
            conn.execute(
                """INSERT OR IGNORE INTO personnel_assignments
                   (id,person_id,position_id,is_primary,start_date,end_date,row_version,updated_at,updated_by)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (assignment_id, row["id"], position_id, 1, "", "", 1, now, None),
            )

    def _ensure_position_projection(self, conn: sqlite3.Connection, values: dict[str, str],
                                    actor_id: str | None, now: str) -> str | None:
        unit_title = values.get("organizational_unit", "").strip()
        position_code = values.get("position_code", "").strip()
        position_title = values.get("position_title", "").strip()
        location = values.get("actual_location", "").strip()
        if not position_code and not position_title:
            return None
        unit_id = None
        if unit_title:
            unit_id = self._projection_id("unit", unit_title)
            unit_code = "U-" + hashlib.sha256(unit_title.encode("utf-8")).hexdigest()[:8].upper()
            conn.execute(
                """INSERT INTO organizational_units
                   (id,code,title,parent_id,unit_type,location,is_active,sort_order,row_version,updated_at,updated_by)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET title=excluded.title,location=excluded.location,
                     is_active=1,updated_at=excluded.updated_at,updated_by=excluded.updated_by""",
                (unit_id, unit_code, unit_title, None, "واحد سازمانی", location, 1, 0, 1, now, actor_id),
            )
        stable_position = position_code or f"{unit_title}|{position_title}"
        position_id = self._projection_id("position", stable_position)
        stored_code = position_code or ("P-" + hashlib.sha256(stable_position.encode("utf-8")).hexdigest()[:8].upper())
        conn.execute(
            """INSERT INTO positions(id,code,title,unit_id,post_type,location,status,row_version,updated_at,updated_by)
               VALUES(?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET code=excluded.code,title=excluded.title,unit_id=excluded.unit_id,
                 location=excluded.location,status='active',updated_at=excluded.updated_at,updated_by=excluded.updated_by""",
            (position_id, stored_code, position_title or stored_code, unit_id, "", location, "active", 1, now, actor_id),
        )
        return position_id

    def _sync_person_projection(self, conn: sqlite3.Connection, person_id: str, values: dict[str, str],
                                actor_id: str | None, now: str, *, effective_date: str = "",
                                assignment_id: str | None = None) -> tuple[str | None, str | None]:
        """Synchronize current projection while preserving every prior assignment.

        ``end_date`` is an effective boundary: the former assignment ceased to
        be current when the replacement became effective.  It is intentionally
        stored as supplied text because deployments may use Jalali dates.
        """
        position_id = self._ensure_position_projection(conn, values, actor_id, now)
        current = conn.execute(
            "SELECT id,position_id FROM personnel_assignments WHERE person_id=? AND is_primary=1 AND end_date=''",
            (person_id,),
        ).fetchone()
        if current and current["position_id"] == position_id:
            conn.execute("UPDATE personnel_assignments SET updated_at=?,updated_by=? WHERE id=?",
                         (now, actor_id, current["id"]))
            return str(current["id"]), str(current["id"])
        boundary = effective_date.strip() or now[:10]
        from_id = str(current["id"]) if current else None
        if current:
            conn.execute(
                "UPDATE personnel_assignments SET end_date=?,row_version=row_version+1,updated_at=?,updated_by=? WHERE id=?",
                (boundary, now, actor_id, current["id"]),
            )
        if position_id is None:
            return from_id, None
        new_id = assignment_id or self._projection_id("assignment", f"{person_id}|{secrets.token_hex(12)}")
        conn.execute(
            """INSERT INTO personnel_assignments
               (id,person_id,position_id,is_primary,start_date,end_date,row_version,updated_at,updated_by)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (new_id, person_id, position_id, 1, boundary if effective_date else "", "", 1, now, actor_id),
        )
        return from_id, new_id

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

    def apply_real_data_import(
        self,
        people: list[dict[str, str]],
        named_positions: list[dict[str, str]],
        *,
        source_name: str,
        source_digest: str,
        warning_count: int = 0,
        actor_id: str | None = None,
    ) -> dict[str, Any]:
        """Atomically refresh existing Enterprise personnel from reconciled private data.

        The import deliberately requires an exact personnel-number set match. It
        never guesses inserts/deletes, never replaces chart JSON, and records one
        auditable batch. Callers must create and verify a database backup first.
        """
        incoming = {str(row.get("personnel_no", "")).strip(): row for row in people}
        if not incoming or "" in incoming or len(incoming) != len(people):
            raise ValueError("Import requires unique, non-empty personnel numbers.")

        now = utc_now()
        batch_id = "import-" + secrets.token_hex(12)
        updated = 0
        marked_named = 0
        with self.write() as conn:
            existing_rows = conn.execute(
                "SELECT * FROM personnel ORDER BY personnel_no"
            ).fetchall()
            existing = {str(row["personnel_no"]): row for row in existing_rows}
            if set(existing) != set(incoming):
                raise ValueError(
                    "Production import blocked: source and target personnel-number sets differ "
                    f"(source={len(incoming)}, target={len(existing)}, "
                    f"source_only={len(set(incoming) - set(existing))}, "
                    f"target_only={len(set(existing) - set(incoming))})."
                )

            for personnel_no in sorted(incoming):
                source = incoming[personnel_no]
                old = existing[personnel_no]

                def value(name: str, fallback: str = "") -> str:
                    candidate = str(source.get(name, "") or "").strip()
                    return candidate if candidate else str(old[fallback or name] or "").strip()

                first_name = value("first_name")
                last_name = value("last_name")
                full_name = " ".join(part for part in (first_name, last_name) if part).strip() or str(old["full_name"])
                values = {
                    "organizational_unit": value("org_unit", "organizational_unit"),
                    "position_code": value("position_no", "position_code"),
                    "position_title": value("position_title"),
                    "employment_group": value("employment_type", "employment_group"),
                    "actual_location": value("location", "actual_location"),
                }
                new_version = int(old["row_version"]) + 1
                conn.execute(
                    """UPDATE personnel SET first_name=?,last_name=?,full_name=?,organizational_unit=?,
                       position_code=?,position_title=?,employment_group=?,actual_location=?,
                       row_version=?,updated_at=?,updated_by=? WHERE id=? AND row_version=?""",
                    (
                        first_name, last_name, full_name, values["organizational_unit"],
                        values["position_code"], values["position_title"], values["employment_group"],
                        values["actual_location"], new_version, now, actor_id, old["id"], old["row_version"],
                    ),
                )
                if conn.execute("SELECT changes()").fetchone()[0] != 1:
                    raise ConflictError(f"Personnel import conflict for batch {batch_id}.")
                self._sync_person_projection(conn, str(old["id"]), values, actor_id, now)
                updated += 1

            for item in named_positions:
                position_no = str(item.get("position_no", "")).strip()
                occupant_no = str(item.get("occupant_personnel_no", "")).strip()
                post_type = str(item.get("position_type", "")).strip()
                row = conn.execute(
                    """SELECT p.id,p.row_version,pe.personnel_no
                       FROM positions p
                       JOIN personnel_assignments a ON a.position_id=p.id AND a.is_primary=1 AND a.end_date=''
                       JOIN personnel pe ON pe.id=a.person_id
                       WHERE p.code=?""",
                    (position_no,),
                ).fetchone()
                if row is None or str(row["personnel_no"]) != occupant_no:
                    raise ValueError("Named-position assignment does not match the Enterprise target.")
                conn.execute(
                    "UPDATE positions SET post_type=?,row_version=row_version+1,updated_at=?,updated_by=? WHERE id=?",
                    (post_type, now, actor_id, row["id"]),
                )
                marked_named += 1

            result = {
                "batch_id": batch_id,
                "updated_personnel": updated,
                "named_position_assignments": marked_named,
                "source_digest": source_digest,
            }
            conn.execute(
                """INSERT INTO import_batches(id,source_name,source_kind,mode,row_count,accepted_count,
                   warning_count,error_count,summary_json,created_by,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    batch_id, source_name, "private-workbooks", "production-apply", len(people), updated,
                    max(0, int(warning_count)), 0, canonical(result), actor_id, now,
                ),
            )
            self._record(conn, actor_id, "production_import", "import_batch", batch_id, None, result, 1)
        return result

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
            result: list[dict[str, Any]] = []
            for row in rows:
                item = dict(row)
                base = {entry[0] for entry in conn.execute(
                    "SELECT permission FROM role_permissions WHERE role=?", (item["role"],)
                )}
                overrides = {
                    entry["permission"]: entry["effect"]
                    for entry in conn.execute(
                        "SELECT permission,effect FROM user_permissions WHERE user_id=?", (item["id"],)
                    )
                }
                for permission, effect in overrides.items():
                    if effect == "allow":
                        base.add(permission)
                    else:
                        base.discard(permission)
                item["permissions"] = sorted(base)
                item["permission_overrides"] = overrides
                result.append(item)
        return result

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
            target = conn.execute("SELECT role FROM users WHERE id=?", (target_user_id,)).fetchone()
            if not target:
                raise ValueError("کاربر پیدا نشد.")
            if target["role"] == "owner":
                raise ValueError("دسترسی‌های مالک اصلی قابل محدودسازی نیست.")
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
            units = conn.execute("SELECT COUNT(*) FROM organizational_units WHERE is_active=1").fetchone()[0]
            positions = conn.execute("SELECT COUNT(*) FROM positions WHERE status='active'").fetchone()[0]
            unassigned = conn.execute(
                """SELECT COUNT(*) FROM personnel p WHERE NOT EXISTS (
                    SELECT 1 FROM personnel_assignments a
                    WHERE a.person_id=p.id AND a.is_primary=1 AND a.end_date=''
                )"""
            ).fetchone()[0]
            revision = conn.execute("SELECT COALESCE(MAX(revision),0) FROM change_feed").fetchone()[0]
        return {"personnel": total, "active": active, "units": units, "positions": positions,
                "unassigned": unassigned, "revision": revision}

    @staticmethod
    def _profile_text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, list):
            parts = [Repository._profile_text(item) for item in value]
            return "، ".join(part for part in parts if part)
        if isinstance(value, dict):
            for key in ("title", "label", "value", "level", "degree", "name"):
                text = Repository._profile_text(value.get(key))
                if text:
                    return text
        return ""

    @staticmethod
    def _profile_value(profile: dict[str, Any], keys: tuple[str, ...]) -> Any:
        normalized = {str(key).strip().lower().replace("-", "_"): value for key, value in profile.items()}
        for key in keys:
            lookup = key.strip().lower().replace("-", "_")
            if lookup in normalized and normalized[lookup] not in (None, "", [], {}):
                return normalized[lookup]
        return None

    @staticmethod
    def _age_from_profile(profile: dict[str, Any]) -> int | None:
        digits = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
        direct = Repository._profile_value(profile, ("age", "سن"))
        if direct is not None:
            raw = "".join(ch for ch in Repository._profile_text(direct).translate(digits) if ch.isdigit())
            if raw and 15 <= int(raw[:3]) <= 100:
                return int(raw[:3])
        birth = Repository._profile_value(profile, (
            "birth_date", "date_of_birth", "birth_year", "سال تولد", "تاریخ تولد", "تاريخ تولد",
        ))
        if birth is None:
            return None
        raw = Repository._profile_text(birth).translate(digits)
        numbers = [int(part) for part in raw.replace("-", "/").split("/") if part.isdigit()]
        if not numbers:
            return None
        year = numbers[0]
        current = dt.datetime.now(UTC).year
        age = (current - 621 - year) if 1250 <= year <= 1500 else current - year
        return age if 15 <= age <= 100 else None

    def analytics(self) -> dict[str, Any]:
        """Return aggregate-only HR analytics for the native v4.9 dashboards.

        The response deliberately excludes personnel identifiers and raw profile
        fields. Optional age/education values are read from ``extra_json`` when
        a private deployment has imported them; public demo builds therefore
        exercise the same UI with explicit missing-data states.
        """
        with self.connect() as conn:
            summary = self.stats()
            page = conn.execute(
                "SELECT approved_fixed_posts,approved_named_posts,approved_total_posts FROM chart_pages WHERE page_no=1"
            ).fetchone()
            chart_pages = int(conn.execute("SELECT COUNT(*) FROM chart_pages").fetchone()[0])
            profiles = conn.execute("SELECT extra_json FROM personnel").fetchall()
            quality = {
                "missing_unit": int(conn.execute(
                    "SELECT COUNT(*) FROM personnel WHERE TRIM(organizational_unit)=''"
                ).fetchone()[0]),
                "missing_position": int(conn.execute(
                    "SELECT COUNT(*) FROM personnel WHERE TRIM(position_code)='' AND TRIM(position_title)=''"
                ).fetchone()[0]),
                "missing_location": int(conn.execute(
                    "SELECT COUNT(*) FROM personnel WHERE TRIM(actual_location)=''"
                ).fetchone()[0]),
                "missing_gender": int(conn.execute(
                    "SELECT COUNT(*) FROM personnel WHERE TRIM(gender)=''"
                ).fetchone()[0]),
            }
            unit_rows = conn.execute(
                """SELECT CASE WHEN TRIM(p.organizational_unit)='' THEN 'ثبت‌نشده' ELSE TRIM(p.organizational_unit) END AS unit,
                          COUNT(*) AS personnel,
                          SUM(CASE WHEN TRIM(p.position_code)='' AND TRIM(p.position_title)='' THEN 1 ELSE 0 END) AS unassigned
                   FROM personnel p GROUP BY unit ORDER BY personnel DESC,unit LIMIT 20"""
            ).fetchall()

        education: dict[str, int] = {}
        age_bands = {"کمتر از ۳۰": 0, "۳۰ تا ۳۹": 0, "۴۰ تا ۴۹": 0, "۵۰ تا ۵۹": 0, "۶۰ و بیشتر": 0}
        known_age = 0
        for row in profiles:
            try:
                profile = json.loads(row["extra_json"] or "{}")
            except (TypeError, json.JSONDecodeError):
                profile = {}
            if not isinstance(profile, dict):
                profile = {}
            degree = self._profile_text(self._profile_value(profile, (
                "education", "education_level", "degree", "degree_title", "مدرک تحصیلی", "مقطع تحصیلی",
            )))
            if degree:
                education[degree] = education.get(degree, 0) + 1
            age = self._age_from_profile(profile)
            if age is not None:
                known_age += 1
                if age < 30:
                    age_bands["کمتر از ۳۰"] += 1
                elif age < 40:
                    age_bands["۳۰ تا ۳۹"] += 1
                elif age < 50:
                    age_bands["۴۰ تا ۴۹"] += 1
                elif age < 60:
                    age_bands["۵۰ تا ۵۹"] += 1
                else:
                    age_bands["۶۰ و بیشتر"] += 1

        total = int(summary["personnel"])
        quality["missing_education"] = max(0, total - sum(education.values()))
        quality["missing_age"] = max(0, total - known_age)
        summary.update({
            "chart_pages": chart_pages,
            "approved_fixed_posts": int(page[0] or 0) if page else 0,
            "approved_named_posts": int(page[1] or 0) if page else 0,
            "approved_chart_total": int(page[2] or 0) if page else 0,
        })
        # Keep the aggregate SQL connection lifetime short; these queries do
        # not expose raw records and are safe to recompute on each refresh.
        with self.connect() as conn:
            def grouped(column: str, limit: int = 20) -> list[dict[str, Any]]:
                rows = conn.execute(
                    f"""SELECT CASE WHEN TRIM({column})='' THEN 'ثبت‌نشده' ELSE TRIM({column}) END AS label,
                               COUNT(*) AS count
                        FROM personnel GROUP BY label ORDER BY count DESC,label LIMIT ?""",
                    (limit,),
                ).fetchall()
                return [{"label": row["label"], "count": int(row["count"])} for row in rows]

            distributions = {
                "employment": grouped("employment_group"),
                "employment_subtype": grouped("employment_subtype"),
                "status": grouped("status"),
                "gender": grouped("gender"),
                "unit": grouped("organizational_unit"),
                "location": grouped("actual_location"),
                "activity_area": grouped("activity_area"),
                "education": [
                    {"label": label, "count": count}
                    for label, count in sorted(education.items(), key=lambda item: (-item[1], item[0]))
                ],
                "age": [{"label": label, "count": count} for label, count in age_bands.items()],
            }
        return {
            "summary": summary,
            "distributions": distributions,
            "quality": quality,
            "unit_comparison": [
                {"unit": row["unit"], "personnel": int(row["personnel"]), "unassigned": int(row["unassigned"] or 0)}
                for row in unit_rows
            ],
            "generated_at": utc_now(),
        }

    def migration_status(self) -> dict[str, Any]:
        with self.connect() as conn:
            metadata = dict(conn.execute(
                "SELECT key,value FROM metadata WHERE key IN ('dataset_kind','schema_version','product_id','schema_generation')"
            ))
            personnel = int(conn.execute("SELECT COUNT(*) FROM personnel").fetchone()[0])
            chart_pages = int(conn.execute("SELECT COUNT(*) FROM chart_pages").fetchone()[0])
            page = conn.execute(
                "SELECT approved_fixed_posts,approved_named_posts,approved_total_posts FROM chart_pages WHERE page_no=1"
            ).fetchone()
            backup = conn.execute(
                "SELECT created_at,filename,integrity_ok,kind FROM backup_catalog ORDER BY id DESC LIMIT 1"
            ).fetchone()
        chart = {
            "fixed": int(page[0] or 0) if page else 0,
            "named": int(page[1] or 0) if page else 0,
            "total": int(page[2] or 0) if page else 0,
            "pages": chart_pages,
        }
        return {
            "dataset_kind": metadata.get("dataset_kind", "unknown"),
            "schema_version": int(metadata.get("schema_version", "0")),
            "schema_generation": metadata.get("schema_generation", ""),
            "personnel": personnel,
            "chart": chart,
            "last_backup": dict(backup) if backup else None,
            "enterprise_target_ready": personnel == 1356 and chart["total"] == 568,
            "expected": {"personnel": 1356, "fixed": 536, "named": 32, "total": 568},
        }

    def organization_summary(self) -> dict[str, int]:
        with self.connect() as conn:
            units = conn.execute("SELECT COUNT(*) FROM organizational_units WHERE is_active=1").fetchone()[0]
            root_units = conn.execute(
                "SELECT COUNT(*) FROM organizational_units WHERE is_active=1 AND parent_id IS NULL"
            ).fetchone()[0]
            positions = conn.execute("SELECT COUNT(*) FROM positions WHERE status='active'").fetchone()[0]
            occupied = conn.execute(
                """SELECT COUNT(DISTINCT position_id) FROM personnel_assignments
                   WHERE is_primary=1 AND end_date=''"""
            ).fetchone()[0]
        return {"units": units, "root_units": root_units, "positions": positions,
                "occupied_positions": occupied, "vacant_positions": max(0, positions - occupied)}

    def list_units(self, query: str = "") -> list[dict[str, Any]]:
        like = f"%{query.strip()}%"
        where = "" if not query.strip() else "WHERE u.title LIKE ? OR u.code LIKE ? OR u.location LIKE ?"
        params: tuple[Any, ...] = () if not where else (like, like, like)
        with self.connect() as conn:
            rows = conn.execute(
                f"""SELECT u.id,u.code,u.title,u.parent_id,u.unit_type,u.location,u.is_active,u.sort_order,
                    u.row_version,
                    (SELECT COUNT(*) FROM positions p WHERE p.unit_id=u.id AND p.status='active') AS positions_count,
                    (SELECT COUNT(*) FROM personnel_assignments a JOIN positions p2 ON p2.id=a.position_id
                       WHERE p2.unit_id=u.id AND a.is_primary=1 AND a.end_date='') AS assigned_count
                    FROM organizational_units u {where}
                    ORDER BY COALESCE(u.parent_id,''),u.sort_order,u.title,u.code""", params
            ).fetchall()
        return [dict(row) for row in rows]

    def get_unit(self, unit_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """SELECT u.*, parent.title AS parent_title
                   FROM organizational_units u LEFT JOIN organizational_units parent ON parent.id=u.parent_id
                   WHERE u.id=?""", (unit_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_positions(self, query: str = "", unit_id: str = "", occupancy: str = "") -> dict[str, Any]:
        clauses: list[str] = []
        params: list[Any] = []
        if query.strip():
            like = f"%{query.strip()}%"
            clauses.append("(p.code LIKE ? OR p.title LIKE ? OR u.title LIKE ? OR p.location LIKE ?)")
            params.extend((like, like, like, like))
        if unit_id.strip():
            clauses.append("p.unit_id=?")
            params.append(unit_id.strip())
        if occupancy == "occupied":
            clauses.append("a.person_id IS NOT NULL")
        elif occupancy == "vacant":
            clauses.append("a.person_id IS NULL")
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        with self.connect() as conn:
            rows = conn.execute(
                f"""SELECT p.id,p.code,p.title,p.unit_id,u.title AS unit_title,p.post_type,p.location,p.status,
                    p.row_version,a.person_id,pe.personnel_no,pe.full_name AS occupant_name
                    FROM positions p
                    LEFT JOIN organizational_units u ON u.id=p.unit_id
                    LEFT JOIN personnel_assignments a ON a.position_id=p.id AND a.is_primary=1 AND a.end_date=''
                    LEFT JOIN personnel pe ON pe.id=a.person_id
                    {where}
                    ORDER BY u.title,p.title,p.code""", tuple(params)
            ).fetchall()
        items = [dict(row) for row in rows]
        return {"items": items, "total": len(items)}

    def get_position(self, position_id: str) -> dict[str, Any] | None:
        result = self.list_positions()
        return next((item for item in result["items"] if item["id"] == position_id), None)

    def list_personnel(self, query: str = "", limit: int = 200, offset: int = 0,
                       *, unit: str = "", employment: str = "", status: str = "",
                       location: str = "") -> dict[str, Any]:
        limit = max(1, min(limit, 1000))
        offset = max(0, offset)
        clauses: list[str] = []
        params: list[Any] = []
        if query.strip():
            like = f"%{query.strip()}%"
            clauses.append("(personnel_no LIKE ? OR full_name LIKE ? OR organizational_unit LIKE ? OR position_title LIKE ?)")
            params.extend((like, like, like, like))
        for column, value in (("organizational_unit", unit), ("employment_group", employment),
                              ("status", status), ("actual_location", location)):
            if value.strip():
                clauses.append(f"{column}=?")
                params.append(value.strip())
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        with self.connect() as conn:
            total = conn.execute(f"SELECT COUNT(*) FROM personnel {where}", tuple(params)).fetchone()[0]
            rows = conn.execute(
                f"""SELECT id,personnel_no,first_name,last_name,full_name,gender,organizational_unit,
                    position_code,position_title,employment_group,employment_subtype,status,
                    activity_area,actual_location,company,chart_page_no,chart_node_id,row_version,updated_at
                    FROM personnel {where} ORDER BY full_name,personnel_no LIMIT ? OFFSET ?""",
                (*params, limit, offset),
            ).fetchall()
            facets = {
                "units": [r[0] for r in conn.execute("SELECT DISTINCT organizational_unit FROM personnel WHERE organizational_unit<>'' ORDER BY organizational_unit")],
                "employment": [r[0] for r in conn.execute("SELECT DISTINCT employment_group FROM personnel WHERE employment_group<>'' ORDER BY employment_group")],
                "statuses": [r[0] for r in conn.execute("SELECT DISTINCT status FROM personnel WHERE status<>'' ORDER BY status")],
                "locations": [r[0] for r in conn.execute("SELECT DISTINCT actual_location FROM personnel WHERE actual_location<>'' ORDER BY actual_location")],
            }
        return {"items": [dict(row) for row in rows], "total": total, "limit": limit, "offset": offset,
                "facets": facets}

    def get_person(self, person_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM personnel WHERE id=?", (person_id,)).fetchone()
        if not row:
            return None
        result = dict(row)
        result["extra"] = json.loads(result.pop("extra_json") or "{}")
        with self.connect() as conn:
            assignment = conn.execute(
                """SELECT a.id AS assignment_id,a.start_date,a.end_date,p.id AS position_id,p.code AS normalized_position_code,
                    p.title AS normalized_position_title,p.post_type,p.location AS position_location,
                    u.id AS unit_id,u.code AS unit_code,u.title AS unit_title,u.unit_type,u.location AS unit_location
                    FROM personnel_assignments a
                    JOIN positions p ON p.id=a.position_id
                    LEFT JOIN organizational_units u ON u.id=p.unit_id
                    WHERE a.person_id=? AND a.is_primary=1 AND a.end_date='' LIMIT 1""", (person_id,)
            ).fetchone()
        result["assignment"] = dict(assignment) if assignment else None
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
        raw_chart_page = payload.get("chart_page_no")
        chart_page_text = "" if raw_chart_page is None else str(raw_chart_page).strip()
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
            self._sync_person_projection(conn, person_id, values, actor_id, now)
            self._record(conn, actor_id, action, "personnel", person_id, before, after, new_version)
        return self.get_person(person_id) or after

    MOVEMENT_TYPES = {
        "appointment", "transfer", "position_change", "unit_change", "location_change",
        "acting", "retirement", "service_exit", "service_return", "correction", "other",
    }

    def _current_assignment_snapshot(self, conn: sqlite3.Connection, person_id: str) -> dict[str, Any] | None:
        row = conn.execute(
            """SELECT a.id AS assignment_id,a.start_date,a.end_date,p.id AS position_id,p.code AS position_code,
                      p.title AS position_title,p.location AS position_location,
                      u.id AS unit_id,u.code AS unit_code,u.title AS unit_title
               FROM personnel_assignments a
               JOIN positions p ON p.id=a.position_id
               LEFT JOIN organizational_units u ON u.id=p.unit_id
               WHERE a.person_id=? AND a.is_primary=1 AND a.end_date='' LIMIT 1""",
            (person_id,),
        ).fetchone()
        return dict(row) if row else None

    def list_personnel_movements(self, person_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT id,person_id,movement_type,effective_date,order_no,order_date,reason,note,
                          from_assignment_id,to_assignment_id,before_json,after_json,created_at,created_by,
                          reversed_at,reversed_by,reversal_reason,row_version
                   FROM personnel_movements WHERE person_id=?
                   ORDER BY effective_date DESC,created_at DESC,id DESC""",
                (person_id,),
            ).fetchall()
        result=[]
        for row in rows:
            item=dict(row)
            item["before"] = json.loads(item.pop("before_json") or "{}")
            item["after"] = json.loads(item.pop("after_json") or "{}")
            item["is_reversed"] = bool(item.get("reversed_at"))
            result.append(item)
        return result

    def register_personnel_movement(self, person_id: str, payload: dict[str, Any], actor_id: str) -> dict[str, Any]:
        movement_type = str(payload.get("movement_type", "")).strip()
        if movement_type not in self.MOVEMENT_TYPES:
            raise ValueError("نوع جابه‌جایی معتبر نیست.")
        effective_date = str(payload.get("effective_date", "")).strip()
        if not effective_date:
            raise ValueError("تاریخ اجرای جابه‌جایی الزامی است.")
        movement_id = str(payload.get("id") or secrets.token_hex(16))
        now = utc_now()
        with self.write() as conn:
            row = conn.execute("SELECT * FROM personnel WHERE id=?", (person_id,)).fetchone()
            if not row:
                raise ValueError("پرسنل پیدا نشد.")
            expected = int(payload.get("row_version", 0))
            if expected != int(row["row_version"]):
                raise ConflictError("پرونده پرسنل تغییر کرده است؛ جابه‌جایی ثبت نشد.")
            before_person = dict(row)
            before_assignment = self._current_assignment_snapshot(conn, person_id)
            values = {
                "organizational_unit": str(payload.get("organizational_unit", row["organizational_unit"])).strip(),
                "position_code": str(payload.get("position_code", row["position_code"])).strip(),
                "position_title": str(payload.get("position_title", row["position_title"])).strip(),
                "actual_location": str(payload.get("actual_location", row["actual_location"])).strip(),
            }
            status = str(payload.get("status", row["status"])).strip()
            if movement_type in {"retirement", "service_exit"} and "position_code" not in payload and "position_title" not in payload:
                values["position_code"] = ""
                values["position_title"] = ""
            new_version = expected + 1
            conn.execute(
                """UPDATE personnel SET organizational_unit=?,position_code=?,position_title=?,actual_location=?,status=?,
                          row_version=?,updated_at=?,updated_by=? WHERE id=? AND row_version=?""",
                (values["organizational_unit"], values["position_code"], values["position_title"],
                 values["actual_location"], status, new_version, now, actor_id, person_id, expected),
            )
            desired_assignment_id = self._projection_id("assignment", f"{person_id}|movement|{movement_id}")
            from_id, to_id = self._sync_person_projection(
                conn, person_id, values, actor_id, now, effective_date=effective_date,
                assignment_id=desired_assignment_id,
            )
            after_assignment = self._current_assignment_snapshot(conn, person_id)
            before = {
                "person": {k: before_person.get(k) for k in (
                    "organizational_unit", "position_code", "position_title", "actual_location", "status", "row_version")},
                "assignment": before_assignment,
            }
            after = {
                "person": {**values, "status": status, "row_version": new_version},
                "assignment": after_assignment,
            }
            conn.execute(
                """INSERT INTO personnel_movements
                   (id,person_id,movement_type,effective_date,order_no,order_date,reason,note,
                    from_assignment_id,to_assignment_id,before_json,after_json,created_at,created_by,row_version)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)""",
                (movement_id, person_id, movement_type, effective_date,
                 str(payload.get("order_no", "")).strip(), str(payload.get("order_date", "")).strip(),
                 str(payload.get("reason", "")).strip(), str(payload.get("note", "")).strip(),
                 from_id, to_id, canonical(before), canonical(after), now, actor_id),
            )
            self._record(conn, actor_id, "movement", "personnel_movement", movement_id, before, after, 1)
            self._record(conn, actor_id, "movement_update", "personnel", person_id, before_person,
                         {**after["person"], "id": person_id}, new_version)
        return {"movement": self.list_personnel_movements(person_id)[0], "person": self.get_person(person_id)}

    def reverse_personnel_movement(self, movement_id: str, reason: str, actor_id: str) -> dict[str, Any]:
        reason = reason.strip()
        if not reason:
            raise ValueError("علت ابطال جابه‌جایی الزامی است.")
        now = utc_now()
        with self.write() as conn:
            movement = conn.execute("SELECT * FROM personnel_movements WHERE id=?", (movement_id,)).fetchone()
            if not movement:
                raise ValueError("جابه‌جایی پیدا نشد.")
            if movement["reversed_at"]:
                raise ValueError("این جابه‌جایی قبلاً ابطال شده است.")
            newer = conn.execute(
                """SELECT 1 FROM personnel_movements WHERE person_id=? AND reversed_at IS NULL
                   AND (created_at>? OR (created_at=? AND id>?)) LIMIT 1""",
                (movement["person_id"], movement["created_at"], movement["created_at"], movement_id),
            ).fetchone()
            if newer:
                raise ConflictError("فقط آخرین جابه‌جایی فعال قابل ابطال است.")
            person = conn.execute("SELECT * FROM personnel WHERE id=?", (movement["person_id"],)).fetchone()
            if not person:
                raise ValueError("پرونده پرسنل پیدا نشد.")
            before = json.loads(movement["before_json"] or "{}")
            before_person = before.get("person", {}) if isinstance(before, dict) else {}
            to_id = movement["to_assignment_id"]
            from_id = movement["from_assignment_id"]
            if to_id:
                conn.execute(
                    "UPDATE personnel_assignments SET end_date=?,row_version=row_version+1,updated_at=?,updated_by=? WHERE id=? AND end_date=''",
                    (now[:10], now, actor_id, to_id),
                )
            if from_id:
                conn.execute(
                    "UPDATE personnel_assignments SET end_date='',row_version=row_version+1,updated_at=?,updated_by=? WHERE id=?",
                    (now, actor_id, from_id),
                )
            new_version = int(person["row_version"]) + 1
            conn.execute(
                """UPDATE personnel SET organizational_unit=?,position_code=?,position_title=?,actual_location=?,status=?,
                          row_version=?,updated_at=?,updated_by=? WHERE id=?""",
                (str(before_person.get("organizational_unit", "")), str(before_person.get("position_code", "")),
                 str(before_person.get("position_title", "")), str(before_person.get("actual_location", "")),
                 str(before_person.get("status", "")), new_version, now, actor_id, movement["person_id"]),
            )
            conn.execute(
                """UPDATE personnel_movements SET reversed_at=?,reversed_by=?,reversal_reason=?,row_version=row_version+1
                   WHERE id=?""",
                (now, actor_id, reason, movement_id),
            )
            after={"reversed": True, "reason": reason, "person": before_person}
            self._record(conn, actor_id, "reverse", "personnel_movement", movement_id, dict(movement), after,
                         int(movement["row_version"]) + 1)
            self._record(conn, actor_id, "movement_reverse", "personnel", movement["person_id"], dict(person),
                         {**before_person, "row_version": new_version}, new_version)
        movements=self.list_personnel_movements(str(movement["person_id"]))
        current=next(item for item in movements if item["id"]==movement_id)
        return {"movement": current, "person": self.get_person(str(movement["person_id"]))}

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
