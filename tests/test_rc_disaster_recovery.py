import shutil,tempfile,unittest
from pathlib import Path
from sazmanhr.config import validate_database_identity
from sazmanhr.database import Repository
from sazmanhr.operations import restore_database

ROOT=Path(__file__).resolve().parents[1]; SEED=ROOT/'data/seed/sazmanhr-seed.sqlite'
class RcDisasterRecoveryTests(unittest.TestCase):
    def test_secondary_destination_backup_can_restore_primary(self):
        with tempfile.TemporaryDirectory() as td:
            r=Path(td); primary=r/'primary/hrm.sqlite'; primary.parent.mkdir(); shutil.copy2(SEED,primary); repo=Repository(primary)
            secondary=r/'secondary/offsite.sqlite'; repo.backup(secondary,kind='disaster-recovery'); self.assertTrue(secondary.is_file())
            primary.write_bytes(b'corrupt-primary'); safety=restore_database(primary,secondary); validate_database_identity(primary); self.assertTrue(safety.exists())
    def test_corrupt_backup_is_rejected_without_replacing_primary(self):
        with tempfile.TemporaryDirectory() as td:
            r=Path(td); primary=r/'hrm.sqlite'; shutil.copy2(SEED,primary); before=primary.read_bytes(); bad=r/'bad.sqlite'; bad.write_bytes(b'not sqlite')
            with self.assertRaisesRegex(RuntimeError,'integrity failed'): restore_database(primary,bad)
            self.assertEqual(primary.read_bytes(),before)
