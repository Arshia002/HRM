import tempfile
import unittest
from pathlib import Path

from sazmanhr.database import Repository
from sazmanhr.server import ensure_initial_owner, main
from sazmanhr.security import validate_password


class HRMBootstrapTests(unittest.TestCase):
    def test_random_bootstrap_is_only_for_initial_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            seed = Path(__file__).resolve().parents[1] / "data" / "seed" / "sazmanhr-seed.sqlite"
            self.assertEqual(main(["--data-dir", str(root), "--seed", str(seed), "--init-only"]), 0)
            db = root / "hrm.sqlite"
            repo = Repository(db)
            # The random secret is written only to the protected first-login notice.
            notice = (root / "FIRST_LOGIN.txt").read_text(encoding="utf-8")
            generated = next(
                line.split(":", 1)[1].strip()
                for line in notice.splitlines()
                if line.startswith("Password:")
            )
            validate_password(generated)
            session = repo.authenticate("arshia.shahbazi", generated, "127.0.0.1")
            self.assertEqual(session["user"]["must_change_password"], 1)
            repo.change_password(session["user"]["id"], generated, "Changed!Password1401")
            with self.assertRaises(Exception):
                repo.authenticate("arshia.shahbazi", generated, "127.0.0.1")
            self.assertFalse((Path(tmp) / "FIRST_LOGIN.txt").exists())


if __name__ == "__main__":
    unittest.main()
