from __future__ import annotations

import contextlib
import sqlite3
import tempfile
import unittest
from pathlib import Path

from sazmanhr.config import PRODUCT_ID, SCHEMA_GENERATION, validate_database_identity
from sazmanhr.database import SCHEMA
from sazmanhr.legacy_upgrade import (
    ALPHA4_MIGRATION_PREFIX,
    LEGACY_PRODUCT_ID,
    LEGACY_SCHEMA_GENERATION,
    LegacyUpgradeError,
    classify_database,
    restore_legacy_database_upgrade,
    upgrade_legacy_database,
)
from sazmanhr.migrations import MIGRATIONS, Migration, apply_migrations


def make_alpha4_database(data_dir: Path) -> Path:
    path = data_dir / "hrm.sqlite"
    with contextlib.closing(sqlite3.connect(path)) as conn:
        conn.executescript(SCHEMA)
        apply_migrations(conn, [m for m in MIGRATIONS if m.version <= 5])
        conn.execute(
            "INSERT OR REPLACE INTO metadata(key,value) VALUES('product_id',?)",
            (LEGACY_PRODUCT_ID,),
        )
        conn.execute(
            "INSERT OR REPLACE INTO metadata(key,value) VALUES('schema_generation',?)",
            (LEGACY_SCHEMA_GENERATION,),
        )
        conn.execute(
            "INSERT OR REPLACE INTO metadata(key,value) VALUES('dataset_kind','synthetic-demo')"
        )
        for i in range(12):
            conn.execute(
                "INSERT INTO personnel(id,personnel_no,full_name,updated_at) VALUES(?,?,?,?)",
                (f"p{i}", f"{i:04d}", f"Person {i}", "2026-01-01T00:00:00+00:00"),
            )
        conn.commit()
    return path


class Alpha4LegacyUpgradeTests(unittest.TestCase):
    def test_exact_alpha4_ancestor_upgrades_and_restores(self):
        with tempfile.TemporaryDirectory() as td:
            data_dir = Path(td)
            db = make_alpha4_database(data_dir)
            state = data_dir / "upgrade-state.json"

            self.assertEqual(classify_database(db), "alpha4")
            result = upgrade_legacy_database(data_dir, state)
            self.assertTrue(result["performed"])
            self.assertEqual(result["schema_version"], 9)
            validate_database_identity(db)

            with contextlib.closing(sqlite3.connect(db)) as conn:
                self.assertEqual(
                    dict(conn.execute(
                        "SELECT key,value FROM metadata WHERE key IN "
                        "('product_id','schema_generation','schema_version')"
                    )),
                    {
                        "product_id": PRODUCT_ID,
                        "schema_generation": SCHEMA_GENERATION,
                        "schema_version": "9",
                    },
                )
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM personnel").fetchone()[0], 12)
                self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])

            restored = restore_legacy_database_upgrade(state)
            self.assertTrue(restored["restored"])
            self.assertEqual(classify_database(db), "alpha4")
            with contextlib.closing(sqlite3.connect(db)) as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM personnel").fetchone()[0], 12)
                applied = {
                    int(v): (n, h)
                    for v, n, h in conn.execute(
                        "SELECT version,name,checksum FROM schema_migrations"
                    )
                }
                self.assertEqual(applied, ALPHA4_MIGRATION_PREFIX)

    def test_unknown_legacy_identity_is_rejected_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            data_dir = Path(td)
            db = make_alpha4_database(data_dir)
            with contextlib.closing(sqlite3.connect(db)) as conn:
                conn.execute("UPDATE metadata SET value='unknown-product' WHERE key='product_id'")
                conn.commit()
            with self.assertRaises(LegacyUpgradeError):
                upgrade_legacy_database(data_dir, data_dir / "state.json")

    def test_tampered_alpha4_migration_checksum_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            data_dir = Path(td)
            db = make_alpha4_database(data_dir)
            with contextlib.closing(sqlite3.connect(db)) as conn:
                conn.execute("UPDATE schema_migrations SET checksum='tampered' WHERE version=5")
                conn.commit()
            with self.assertRaises(LegacyUpgradeError):
                upgrade_legacy_database(data_dir, data_dir / "state.json")

    def test_mid_migration_failure_restores_alpha4_database(self):
        with tempfile.TemporaryDirectory() as td:
            data_dir = Path(td)
            db = make_alpha4_database(data_dir)
            state = data_dir / "state.json"
            bad = tuple(m for m in MIGRATIONS if m.version <= 6) + (
                Migration(7, "forced_failure", "THIS IS NOT VALID SQL"),
            )
            with self.assertRaises(Exception):
                upgrade_legacy_database(data_dir, state, migrations=bad)

            self.assertEqual(classify_database(db), "alpha4")
            with contextlib.closing(sqlite3.connect(db)) as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM personnel").fetchone()[0], 12)
                self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                applied = {
                    int(v): (n, h)
                    for v, n, h in conn.execute(
                        "SELECT version,name,checksum FROM schema_migrations"
                    )
                }
                self.assertEqual(applied, ALPHA4_MIGRATION_PREFIX)

    def test_current_database_is_noop(self):
        with tempfile.TemporaryDirectory() as td:
            data_dir = Path(td)
            db = make_alpha4_database(data_dir)
            upgrade_legacy_database(data_dir, data_dir / "state1.json")
            result = upgrade_legacy_database(data_dir, data_dir / "state2.json")
            self.assertFalse(result["performed"])
            self.assertEqual(classify_database(db), "current")
