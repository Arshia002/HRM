import tempfile
import unittest
from pathlib import Path

from sazmanhr.database import Repository
from sazmanhr.server import ensure_initial_owner, main
from sazmanhr.security import validate_password


class HRMBootstrapTests(unittest.TestCase):
    def test_fixed_bootstrap_is_only_for_initial_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            seed = Path(__file__).resolve().parents[1] / "data" / "seed" / "sazmanhr-seed.sqlite"
            self.assertEqual(main(["--data-dir", str(root), "--seed", str(seed), "--init-only"]), 0)
            db = root / "hrm.sqlite"
            repo = Repository(db)
            # main already created the first owner using the HRM bootstrap secret.
            generated = "13811381"
            self.assertEqual(generated, "13811381")
            session = repo.authenticate("arshia.shahbazi", "13811381", "127.0.0.1")
            self.assertEqual(session["user"]["must_change_password"], 1)
            with self.assertRaises(ValueError):
                validate_password("13811381")
            repo.change_password(session["user"]["id"], "13811381", "Changed!Password1401")
            with self.assertRaises(Exception):
                repo.authenticate("arshia.shahbazi", "13811381", "127.0.0.1")
            self.assertFalse((Path(tmp) / "FIRST_LOGIN.txt").exists())


if __name__ == "__main__":
    unittest.main()
