from __future__ import annotations

import contextlib
import hashlib
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from sazmanhr.config import validate_database_identity
from sazmanhr.database import Repository
from sazmanhr.operations import restore_database, sqlite_integrity


ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "data" / "seed" / "sazmanhr-seed.sqlite"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _user_table(conn: sqlite3.Connection) -> str:
    tables = [
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
    ]
    matches: list[str] = []
    for table in tables:
        quoted = table.replace('"', '""')
        columns = {
            str(row[1])
            for row in conn.execute(f'PRAGMA table_info("{quoted}")')
        }
        if {"username", "role"}.issubset(columns):
            matches.append(table)
    if len(matches) != 1:
        raise AssertionError(
            f"expected exactly one username/role table, found {matches}"
        )
    return matches[0]


def _snapshot(path: Path) -> dict[str, object]:
    with contextlib.closing(sqlite3.connect(path)) as conn:
        conn.row_factory = sqlite3.Row
        user_table = _user_table(conn)
        quoted_user_table = user_table.replace('"', '""')

        users = [
            (str(row["username"]), str(row["role"]))
            for row in conn.execute(
                f'SELECT username,role FROM "{quoted_user_table}" ORDER BY username'
            )
        ]
        audit = [
            (
                str(row["user_id"] or ""),
                str(row["action"] or ""),
                str(row["entity_type"] or ""),
                str(row["entity_id"] or ""),
                str(row["occurred_at"] or ""),
                str(row["previous_hash"] or ""),
                str(row["event_hash"] or ""),
            )
            for row in conn.execute(
                """SELECT user_id,action,entity_type,entity_id,occurred_at,
                          previous_hash,event_hash
                   FROM audit_log
                   ORDER BY id"""
            )
        ]

        return {
            "personnel": int(
                conn.execute("SELECT COUNT(*) FROM personnel").fetchone()[0]
            ),
            "assignments": int(
                conn.execute(
                    "SELECT COUNT(*) FROM personnel_assignments"
                ).fetchone()[0]
            ),
            "active_primary_assignments": int(
                conn.execute(
                    """SELECT COUNT(*) FROM personnel_assignments
                       WHERE is_primary=1 AND end_date=''"""
                ).fetchone()[0]
            ),
            "movements": int(
                conn.execute(
                    "SELECT COUNT(*) FROM personnel_movements"
                ).fetchone()[0]
            ),
            "users": users,
            "audit": audit,
        }


class G11BackupRestoreAcceptanceTests(unittest.TestCase):
    def test_verified_backup_restores_independent_environment_without_business_state_loss(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source" / "hrm.sqlite"
            source.parent.mkdir()
            shutil.copy2(SEED, source)

            repo = Repository(source)
            owner = repo.create_user(
                "g11.owner",
                "G11 Super Admin",
                "G11!Owner1500",
                "owner",
                must_change_password=False,
            )
            hr = repo.create_user(
                "g11.hr",
                "G11 HR Admin",
                "G11!HrAdmin1500",
                "admin",
                must_change_password=False,
            )

            assigned = None
            for item in repo.list_personnel(limit=100)["items"]:
                detail = repo.get_person(item["id"])
                if detail.get("assignment"):
                    assigned = detail
                    break
            self.assertIsNotNone(assigned)

            moved = repo.register_personnel_movement(
                assigned["id"],
                {
                    "movement_type": "transfer",
                    "effective_date": "1405/12/01",
                    "order_no": "G11-ORDER-001",
                    "order_date": "1405/11/29",
                    "reason": "G11 backup/restore acceptance",
                    "organizational_unit": "G11 Recovery Unit",
                    "position_code": "G11-POS-001",
                    "position_title": "G11 Recovery Position",
                    "row_version": assigned["row_version"],
                },
                hr["id"],
            )
            self.assertEqual(
                moved["person"]["organizational_unit"],
                "G11 Recovery Unit",
            )
            self.assertTrue(repo.verify_audit_chain())

            backup_dir = root / "backups"
            backup_dir.mkdir()
            backup = repo.backup(
                backup_dir / "g11-verified.sqlite",
                kind="g11-acceptance",
            )
            backup = Path(backup)
            self.assertTrue(backup.is_file())
            backup_hash = _sha256(backup)
            self.assertEqual(sqlite_integrity(backup), (True, "ok"))
            validate_database_identity(backup)

            source_snapshot = _snapshot(source)
            backup_snapshot = _snapshot(backup)

            # The backup must contain the complete business/security state.
            for key in (
                "personnel",
                "assignments",
                "active_primary_assignments",
                "movements",
                "users",
                "audit",
            ):
                self.assertEqual(
                    backup_snapshot[key],
                    source_snapshot[key],
                    key,
                )

            audit_verification = root / "backup-audit-verification.sqlite"
            shutil.copy2(backup, audit_verification)
            backup_repo = Repository(audit_verification)
            self.assertTrue(backup_repo.verify_audit_chain())
            self.assertEqual(_sha256(backup), backup_hash)

            # Independent clean environment: initialize a separate valid DB and
            # deliberately add state that must disappear after restore.
            restored = root / "independent" / "hrm.sqlite"
            restored.parent.mkdir()
            shutil.copy2(SEED, restored)
            clean_repo = Repository(restored)
            clean_repo.create_user(
                "clean.only",
                "Independent Environment Marker",
                "G11!Clean1500",
                "owner",
                must_change_password=False,
            )
            clean_snapshot = _snapshot(restored)
            self.assertIn(
                ("clean.only", "owner"),
                clean_snapshot["users"],
            )

            safety = restore_database(restored, backup)
            self.assertTrue(Path(safety).is_file())
            self.assertEqual(_sha256(backup), backup_hash)

            validate_database_identity(restored)
            self.assertEqual(sqlite_integrity(restored), (True, "ok"))

            restored_snapshot = _snapshot(restored)
            self.assertEqual(restored_snapshot, backup_snapshot)
            self.assertNotIn(
                ("clean.only", "owner"),
                restored_snapshot["users"],
            )
            self.assertIn(
                ("g11.owner", "owner"),
                restored_snapshot["users"],
            )
            self.assertIn(
                ("g11.hr", "admin"),
                restored_snapshot["users"],
            )

            restored_repo = Repository(restored)
            self.assertTrue(restored_repo.verify_audit_chain())

            with contextlib.closing(sqlite3.connect(restored)) as conn:
                self.assertEqual(
                    conn.execute("PRAGMA integrity_check").fetchone()[0],
                    "ok",
                )
                self.assertEqual(
                    conn.execute("PRAGMA foreign_key_check").fetchall(),
                    [],
                )


if __name__ == "__main__":
    unittest.main()
