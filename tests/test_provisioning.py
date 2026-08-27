import contextlib
import hashlib
import io
import logging
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sazmanhr.config import validate_database_identity
from sazmanhr.demo_data import create_demo_seed
from sazmanhr.server import main


class ProvisioningTests(unittest.TestCase):
    def setUp(self):
        self.seed_temp = tempfile.TemporaryDirectory()
        self.seed = Path(self.seed_temp.name) / "hrm-seed.sqlite"
        create_demo_seed(self.seed)

    def tearDown(self):
        self.seed_temp.cleanup()

    def test_identity_validation_closes_sqlite_handle(self):
        opened = []
        real_connect = sqlite3.connect

        def tracked_connect(*args, **kwargs):
            connection = real_connect(*args, **kwargs)
            opened.append(connection)
            return connection

        with patch("sazmanhr.config.sqlite3.connect", side_effect=tracked_connect):
            validate_database_identity(self.seed)
        self.assertEqual(len(opened), 1)
        with self.assertRaises(sqlite3.ProgrammingError):
            opened[0].execute("SELECT 1")

    def test_clean_init_and_verify(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                initialized = main(["--data-dir", str(root), "--seed", str(self.seed), "--init-only"])
                verified = main(["--data-dir", str(root), "--verify-database"])
            self.assertEqual(initialized, 0)
            self.assertEqual(verified, 0)
            self.assertTrue((root / "hrm.sqlite").is_file())
            self.assertTrue((root / "FIRST_LOGIN.txt").is_file())
            server_log = root / "logs" / "server.jsonl"
            server_log.unlink()
            self.assertFalse(server_log.exists())
            self.assertEqual(logging.getLogger("sazmanhr").handlers, [])

    def test_incompatible_database_fails_with_diagnostic_and_no_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            database = root / "hrm.sqlite"
            diagnostic = root / "setup-server.log"
            with contextlib.closing(sqlite3.connect(database)) as conn:
                conn.execute("CREATE TABLE users(id INTEGER PRIMARY KEY, name TEXT)")
                conn.commit()
            before = hashlib.sha256(database.read_bytes()).hexdigest()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                status = main([
                    "--data-dir", str(root), "--seed", str(self.seed), "--init-only",
                    "--diagnostic-log", str(diagnostic),
                ])
            self.assertEqual(status, 1)
            self.assertEqual(hashlib.sha256(database.read_bytes()).hexdigest(), before)
            self.assertIn("IncompatibleDatabaseError", diagnostic.read_text(encoding="utf-8"))
            server_log = root / "logs" / "server.jsonl"
            server_log.unlink()
            self.assertFalse(server_log.exists())
            self.assertEqual(logging.getLogger("sazmanhr").handlers, [])


if __name__ == "__main__":
    unittest.main()
