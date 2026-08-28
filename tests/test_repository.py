import hashlib
import contextlib
import shutil
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sazmanhr.database import AuthenticationError, ConflictError, MfaRequired, PermissionDenied, Repository
from sazmanhr.config import IncompatibleDatabaseError
from sazmanhr.operations import restore_database, sqlite_integrity
from sazmanhr.security import totp_code


PROJECT = Path(__file__).resolve().parents[1]
SEED = PROJECT / "data" / "seed" / "sazmanhr-seed.sqlite"


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "test.sqlite"
        shutil.copy2(SEED, self.db)
        self.repo = Repository(self.db)
        self.password = "Initial!Password1400"
        self.owner = self.repo.create_user(
            "arshia.shahbazi", "ارشیا شهبازی", self.password, "owner", must_change_password=True
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_seed_counts_and_integrity(self):
        stats = self.repo.stats()
        self.assertEqual(stats["personnel"], 36)
        self.assertEqual(len(self.repo.list_chart_pages()), 53)
        self.assertTrue(self.repo.verify_audit_chain())

    def test_connection_context_closes_database_handle(self):
        connection = self.repo.connect()
        with connection as active:
            self.assertEqual(active.execute("SELECT 1").fetchone()[0], 1)
        with self.assertRaises(sqlite3.ProgrammingError):
            connection.execute("SELECT 1")

    def test_legacy_database_is_blocked_without_mutation(self):
        legacy = Path(self.temp.name) / "legacy.sqlite"
        with contextlib.closing(sqlite3.connect(legacy)) as conn:
            conn.execute("CREATE TABLE users(id INTEGER PRIMARY KEY, name TEXT)")
            conn.commit()
        before = hashlib.sha256(legacy.read_bytes()).hexdigest()
        with self.assertRaises(IncompatibleDatabaseError):
            Repository(legacy)
        after = hashlib.sha256(legacy.read_bytes()).hexdigest()
        self.assertEqual(after, before)

    def test_login_and_forced_password_change(self):
        with self.assertRaises(AuthenticationError):
            self.repo.authenticate("arshia.shahbazi", "wrong", "127.0.0.1")
        session = self.repo.authenticate("arshia.shahbazi", self.password, "127.0.0.1")
        self.assertEqual(session["user"]["username"], "arshia.shahbazi")
        self.assertEqual(session["user"]["must_change_password"], 1)
        self.repo.change_password(self.owner["id"], self.password, "Changed!Password1401")
        self.assertEqual(self.repo.session_user(session["token"])["must_change_password"], 0)

    def test_failed_login_counter_is_committed(self):
        for _ in range(5):
            with self.assertRaises(AuthenticationError):
                self.repo.authenticate("arshia.shahbazi", "Definitely!Wrong1500", "10.0.0.8")
        with self.repo.connect() as conn:
            row = conn.execute("SELECT failed_attempts,locked_until FROM users WHERE id=?", (self.owner["id"],)).fetchone()
            failures = conn.execute("SELECT COUNT(*) FROM login_events WHERE username='arshia.shahbazi' AND succeeded=0").fetchone()[0]
        self.assertEqual(row["failed_attempts"], 0)
        self.assertIsNotNone(row["locked_until"])
        self.assertEqual(failures, 5)

    def test_optimistic_concurrency_and_audit(self):
        first = self.repo.list_personnel(limit=1)["items"][0]
        detail = self.repo.get_person(first["id"])
        detail["position_title"] = "عنوان آزمون"
        saved = self.repo.save_person(detail, self.owner["id"])
        self.assertEqual(saved["row_version"], detail["row_version"] + 1)
        with self.assertRaises(ConflictError):
            self.repo.save_person(detail, self.owner["id"])
        self.assertTrue(self.repo.verify_audit_chain())
        changes = self.repo.changes(0)
        self.assertTrue(any(item["entity_type"] == "personnel" for item in changes["items"]))

    def test_dashboard_is_editable(self):
        saved = self.repo.save_widget({
            "title": "اطلاعیه", "widget_type": "text", "config": {"text": "آزمون"},
            "position": 3, "is_enabled": True,
        }, self.owner["id"])
        self.assertEqual(saved["row_version"], 1)
        saved["title"] = "اطلاعیه جدید"
        updated = self.repo.save_widget(saved, self.owner["id"])
        self.assertEqual(updated["row_version"], 2)

    def test_chart_page_can_be_renamed(self):
        page = self.repo.get_chart_page(1)
        page["title"] = "صفحه آزمایشی"
        saved = self.repo.save_chart_page(1, page, self.owner["id"])
        self.assertEqual(saved["title"], "صفحه آزمایشی")
        self.assertEqual(saved["row_version"], 2)
        self.assertTrue(self.repo.verify_audit_chain())

    def test_five_distinct_admin_edits_are_serialized(self):
        people = self.repo.list_personnel(limit=5)["items"]

        def update(item):
            detail = self.repo.get_person(item["id"])
            detail["status"] = "آزمون هم‌زمان"
            return self.repo.save_person(detail, self.owner["id"])

        with ThreadPoolExecutor(max_workers=5) as pool:
            saved = list(pool.map(update, people))
        self.assertEqual(len(saved), 5)
        self.assertTrue(all(item["row_version"] == 2 for item in saved))
        self.assertTrue(self.repo.verify_audit_chain())

    def test_migrations_and_fine_grained_permissions(self):
        with self.repo.connect() as conn:
            versions = [row[0] for row in conn.execute("SELECT version FROM schema_migrations ORDER BY version")]
            schema_version = conn.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()[0]
        self.assertEqual(versions, [2, 3, 4, 5, 6])
        self.assertEqual(schema_version, "6")
        editor = self.repo.create_user("editor.one", "ویرایشگر", "Editor!Password1500", "editor",
                                       must_change_password=False)
        self.repo.require(editor, "edit_personnel")
        self.repo.set_user_permissions(editor["id"], {"edit_personnel": "deny"}, self.owner["id"])
        with self.assertRaises(PermissionDenied):
            self.repo.require(editor, "edit_personnel")

    def test_mfa_and_recovery_code(self):
        setup = self.repo.begin_mfa(self.owner["id"], self.owner["username"], self.password)
        codes = self.repo.confirm_mfa(self.owner["id"], totp_code(setup["secret"]))
        self.assertEqual(len(codes), 8)
        with self.assertRaises(MfaRequired):
            self.repo.authenticate(self.owner["username"], self.password, "127.0.0.1")
        session = self.repo.authenticate(self.owner["username"], self.password, "127.0.0.1",
                                         totp_code(setup["secret"]))
        self.assertTrue(session["token"])
        recovery_session = self.repo.authenticate(self.owner["username"], self.password, "127.0.0.1", codes[0])
        self.assertTrue(recovery_session["token"])
        with self.assertRaises(AuthenticationError):
            self.repo.authenticate(self.owner["username"], self.password, "127.0.0.1", codes[0])

    def test_workflow_notification_backup_and_restore(self):
        workflow = self.repo.create_workflow({
            "workflow_type": "document", "title": "بررسی مدرک", "entity_type": "personnel",
            "entity_id": "F-1771", "assigned_to": self.owner["id"], "payload": {"kind": "identity"},
        }, self.owner["id"])
        transitioned = self.repo.transition_workflow(workflow["id"], "approved", "تأیید شد",
                                                     self.owner["id"], workflow["row_version"])
        self.assertEqual(transitioned["state"], "approved")
        self.assertTrue(self.repo.notifications(self.owner["id"], unread_only=True))
        backup = Path(self.temp.name) / "backups" / "verified.sqlite"
        self.repo.backup(backup, self.owner["id"])
        self.assertTrue(sqlite_integrity(backup)[0])
        first = self.repo.list_personnel(limit=1)["items"][0]
        detail = self.repo.get_person(first["id"])
        original = detail["status"]
        detail["status"] = "پس از پشتیبان"
        self.repo.save_person(detail, self.owner["id"])
        safety = restore_database(self.db, backup)
        self.assertTrue(safety.exists())
        restored = Repository(self.db).get_person(first["id"])
        self.assertEqual(restored["status"], original)


if __name__ == "__main__":
    unittest.main()
