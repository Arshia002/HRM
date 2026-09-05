"""Checksum-verified, ordered database migrations."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    sql: str

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.sql.encode("utf-8")).hexdigest()


MIGRATIONS = (
    Migration(2, "fine_grained_permissions", r"""
CREATE TABLE IF NOT EXISTS permissions (
  name TEXT PRIMARY KEY,
  description TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS role_permissions (
  role TEXT NOT NULL,
  permission TEXT NOT NULL REFERENCES permissions(name) ON DELETE CASCADE,
  PRIMARY KEY(role, permission)
);
CREATE TABLE IF NOT EXISTS user_permissions (
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  permission TEXT NOT NULL REFERENCES permissions(name) ON DELETE CASCADE,
  effect TEXT NOT NULL CHECK(effect IN ('allow','deny')),
  PRIMARY KEY(user_id, permission)
);
"""),
    Migration(3, "backup_catalog_and_operations", r"""
CREATE TABLE IF NOT EXISTS backup_catalog (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  filename TEXT NOT NULL UNIQUE,
  sha256 TEXT NOT NULL,
  size_bytes INTEGER NOT NULL,
  integrity_ok INTEGER NOT NULL CHECK(integrity_ok IN (0,1)),
  created_by TEXT,
  kind TEXT NOT NULL DEFAULT 'manual'
);
CREATE TABLE IF NOT EXISTS operational_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  occurred_at TEXT NOT NULL,
  level TEXT NOT NULL,
  component TEXT NOT NULL,
  event_code TEXT NOT NULL,
  message TEXT NOT NULL,
  details_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_operational_events_time ON operational_events(occurred_at DESC);
"""),
    Migration(4, "workflow_notifications", r"""
CREATE TABLE IF NOT EXISTS workflows (
  id TEXT PRIMARY KEY,
  workflow_type TEXT NOT NULL,
  title TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  state TEXT NOT NULL,
  payload_json TEXT NOT NULL DEFAULT '{}',
  assigned_to TEXT REFERENCES users(id),
  due_at TEXT,
  created_by TEXT REFERENCES users(id),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  row_version INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_workflows_state ON workflows(state, due_at);
CREATE TABLE IF NOT EXISTS workflow_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  workflow_id TEXT NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
  action TEXT NOT NULL,
  from_state TEXT,
  to_state TEXT,
  note TEXT NOT NULL DEFAULT '',
  actor_id TEXT REFERENCES users(id),
  occurred_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notifications (
  id TEXT PRIMARY KEY,
  user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
  severity TEXT NOT NULL CHECK(severity IN ('info','warning','critical')),
  title TEXT NOT NULL,
  message TEXT NOT NULL,
  related_type TEXT,
  related_id TEXT,
  is_read INTEGER NOT NULL DEFAULT 0 CHECK(is_read IN (0,1)),
  created_at TEXT NOT NULL,
  read_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, is_read, created_at DESC);
"""),
    Migration(5, "totp_mfa", r"""
CREATE TABLE IF NOT EXISTS mfa_totp (
  user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  secret_encrypted TEXT NOT NULL,
  is_enabled INTEGER NOT NULL DEFAULT 0 CHECK(is_enabled IN (0,1)),
  created_at TEXT NOT NULL,
  confirmed_at TEXT
);
CREATE TABLE IF NOT EXISTS mfa_recovery_codes (
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  code_hash TEXT NOT NULL,
  used_at TEXT,
  PRIMARY KEY(user_id, code_hash)
);
"""),
    Migration(6, "organization_personnel_core", r"""
CREATE TABLE IF NOT EXISTS organizational_units (
  id TEXT PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  parent_id TEXT REFERENCES organizational_units(id) ON DELETE SET NULL,
  unit_type TEXT NOT NULL DEFAULT '',
  location TEXT NOT NULL DEFAULT '',
  is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
  sort_order INTEGER NOT NULL DEFAULT 0,
  row_version INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL,
  updated_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_org_units_parent ON organizational_units(parent_id, sort_order, title);
CREATE INDEX IF NOT EXISTS idx_org_units_title ON organizational_units(title);
CREATE TABLE IF NOT EXISTS positions (
  id TEXT PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  unit_id TEXT REFERENCES organizational_units(id) ON DELETE SET NULL,
  post_type TEXT NOT NULL DEFAULT '',
  location TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'active',
  row_version INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL,
  updated_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_positions_unit ON positions(unit_id, title, code);
CREATE INDEX IF NOT EXISTS idx_positions_title ON positions(title);
CREATE TABLE IF NOT EXISTS personnel_assignments (
  id TEXT PRIMARY KEY,
  person_id TEXT NOT NULL REFERENCES personnel(id) ON DELETE CASCADE,
  position_id TEXT NOT NULL REFERENCES positions(id) ON DELETE CASCADE,
  is_primary INTEGER NOT NULL DEFAULT 1 CHECK(is_primary IN (0,1)),
  start_date TEXT NOT NULL DEFAULT '',
  end_date TEXT NOT NULL DEFAULT '',
  row_version INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL,
  updated_by TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_assignments_primary_person
  ON personnel_assignments(person_id) WHERE is_primary=1 AND end_date='';
CREATE INDEX IF NOT EXISTS idx_assignments_position ON personnel_assignments(position_id, end_date);
CREATE TABLE IF NOT EXISTS import_batches (
  id TEXT PRIMARY KEY,
  source_name TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  mode TEXT NOT NULL DEFAULT 'dry-run',
  row_count INTEGER NOT NULL DEFAULT 0,
  accepted_count INTEGER NOT NULL DEFAULT 0,
  warning_count INTEGER NOT NULL DEFAULT 0,
  error_count INTEGER NOT NULL DEFAULT 0,
  summary_json TEXT NOT NULL DEFAULT '{}',
  created_by TEXT,
  created_at TEXT NOT NULL
);
"""),
    Migration(7, "personnel_movement_history_and_hr_roles", r"""
CREATE TABLE IF NOT EXISTS personnel_movements (
  id TEXT PRIMARY KEY,
  person_id TEXT NOT NULL REFERENCES personnel(id) ON DELETE CASCADE,
  movement_type TEXT NOT NULL,
  effective_date TEXT NOT NULL,
  order_no TEXT NOT NULL DEFAULT '',
  order_date TEXT NOT NULL DEFAULT '',
  reason TEXT NOT NULL DEFAULT '',
  note TEXT NOT NULL DEFAULT '',
  from_assignment_id TEXT,
  to_assignment_id TEXT,
  before_json TEXT NOT NULL DEFAULT '{}',
  after_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  created_by TEXT REFERENCES users(id),
  reversed_at TEXT,
  reversed_by TEXT REFERENCES users(id),
  reversal_reason TEXT NOT NULL DEFAULT '',
  row_version INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_personnel_movements_person
  ON personnel_movements(person_id, effective_date, created_at);
CREATE INDEX IF NOT EXISTS idx_personnel_movements_order
  ON personnel_movements(order_no, order_date);
DELETE FROM role_permissions WHERE role='admin';
"""),
)


def ensure_migration_table(conn: sqlite3.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS schema_migrations (
        version INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        checksum TEXT NOT NULL,
        applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")


def apply_migrations(conn: sqlite3.Connection, migrations: Iterable[Migration] = MIGRATIONS) -> int:
    ensure_migration_table(conn)
    applied = {row[0]: (row[1], row[2]) for row in conn.execute(
        "SELECT version,name,checksum FROM schema_migrations"
    )}
    latest = 1
    for migration in migrations:
        latest = max(latest, migration.version)
        existing = applied.get(migration.version)
        if existing:
            if existing != (migration.name, migration.checksum):
                raise RuntimeError(f"Migration checksum mismatch at version {migration.version}.")
            continue
        conn.execute("BEGIN IMMEDIATE")
        try:
            for statement in migration.sql.split(";"):
                if statement.strip():
                    conn.execute(statement)
            conn.execute(
                "INSERT INTO schema_migrations(version,name,checksum) VALUES(?,?,?)",
                (migration.version, migration.name, migration.checksum),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    conn.execute("INSERT OR REPLACE INTO metadata(key,value) VALUES('schema_version',?)", (str(latest),))
    return latest
