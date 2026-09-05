from __future__ import annotations
import os
import tempfile
import unittest
from pathlib import Path

from sazmanhr.config import ServerConfig, ensure_database
from sazmanhr.database import Repository
from sazmanhr.operations import BackupScheduler, sqlite_integrity


class FinalOperationsTests(unittest.TestCase):
    def test_server_config_round_trips_secondary_backup_without_changing_defaults(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            config=ServerConfig.load(root)
            self.assertEqual(config.backup_interval_hours,24)
            self.assertEqual(config.backup_retention,30)
            self.assertEqual(config.backup_secondary_dir,"")
            config.backup_secondary_dir=str(root/'secondary')
            config.backup_secondary_retention=12
            config.save(root)
            loaded=ServerConfig.load(root)
            self.assertEqual(loaded.backup_secondary_dir,str(root/'secondary'))
            self.assertEqual(loaded.backup_secondary_retention,12)

    def test_scheduled_backup_creates_verified_secondary_copy(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); data=root/'data'; secondary=root/'secondary'
            repo=Repository(ensure_database(data))
            scheduler=BackupScheduler(repo,24,30,secondary,30)
            primary=scheduler.run_once(); copy=secondary/primary.name
            self.assertTrue(primary.is_file()); self.assertTrue(copy.is_file())
            self.assertEqual(primary.read_bytes(),copy.read_bytes())
            self.assertEqual(sqlite_integrity(copy),(True,'ok'))
            events=repo.operational_events(50)
            backup=[x for x in events if x['event_code']=='backup_ok'][0]
            self.assertTrue(backup['details']['secondary_copy'])

    def test_secondary_retention_is_independent_from_primary_catalog(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); data=root/'data'; secondary=root/'secondary'; secondary.mkdir()
            repo=Repository(ensure_database(data)); scheduler=BackupScheduler(repo,24,30,secondary,3)
            source=repo.backup(root/'source.sqlite',kind='test')
            for i in range(5):
                target=secondary/f'scheduled-2026010{i+1}-010101.sqlite'
                target.write_bytes(source.read_bytes())
                os.utime(target,ns=(1_000_000_000+i,1_000_000_000+i))
            scheduler._copy_to_secondary(source)
            self.assertLessEqual(len(list(secondary.glob('scheduled-*.sqlite'))),3)


if __name__=='__main__': unittest.main()
