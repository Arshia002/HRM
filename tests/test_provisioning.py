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
from sazmanhr.server import main


PROJECT = Path(__file__).resolve().parents[1]
SEED = PROJECT / "data" / "seed" / "sazmanhr-seed.sqlite"


class ProvisioningTests(unittest.TestCase):
    def test_identity_validation_closes_sqlite_handle(self):
        opened = []
        real_connect = sqlite3.connect

        def tracked_connect(*args, **kwargs):
            connection = real_connect(*args, **kwargs)
            opened.append(connection)
            return connection

        with patch("sazmanhr.config.sqlite3.connect", side_effect=tracked_connect):
            validate_database_identity(SEED)
        self.assertEqual(len(opened), 1)
        with self.assertRaises(sqlite3.ProgrammingError):
            opened[0].execute("SELECT 1")

    def test_clean_init_and_verify(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                initialized = main(["--data-dir", str(root), "--seed", str(SEED), "--init-only"])
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
                    "--data-dir", str(root), "--seed", str(SEED), "--init-only",
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
