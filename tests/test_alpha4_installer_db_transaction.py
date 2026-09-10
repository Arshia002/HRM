from __future__ import annotations

import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
ISS = PROJECT / "build" / "windows" / "HRM.iss"


class Alpha4InstallerDatabaseTransactionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = ISS.read_text(encoding="utf-8")
        cls.lower = cls.script.lower()

    def test_database_upgrade_runs_after_service_stop_and_before_init_only(self):
        stop = self.lower.index("service-stop-for-cutover")
        upgrade = self.lower.index("database-upgrade-alpha4")
        init_only = self.lower.index('" --init-only --diagnostic-log "')
        self.assertLess(stop, upgrade)
        self.assertLess(upgrade, init_only)
        self.assertIn("--upgrade-legacy-database", self.lower)
        self.assertIn("--database-upgrade-state-file", self.lower)

    def test_recovery_restores_database_before_old_service_start(self):
        start = self.lower.index("procedure restoreoriginalserviceifneeded")
        end = self.lower.index("procedure recoverserverafterfailure", start)
        recovery = self.lower[start:end]
        db_restore = recovery.index("restoredatabaseupgradeifneeded")
        image_restore = recovery.index("restore-original-service-image")
        service_start = recovery.index("restore-original-service-running")
        self.assertLess(db_restore, image_restore)
        self.assertLess(db_restore, service_start)
        self.assertIn("servicewasrunningbeforeinstall and restoreok", recovery)

    def test_database_restore_is_explicit_and_fail_closed(self):
        self.assertIn("--restore-legacy-database-upgrade", self.lower)
        self.assertIn("restore-database-upgrade", self.lower)
        self.assertIn("databaseupgradeattempted", self.lower)
        self.assertIn("databaseupgradestatepath", self.lower)

    def test_fresh_install_recovery_also_restores_database_if_attempted(self):
        start = self.lower.index("procedure recoverserverafterfailure")
        end = self.lower.index("procedure verifyonelegacyservicedisabled", start)
        recovery = self.lower[start:end]
        self.assertIn("restoredatabaseupgradeifneeded", recovery)

    def test_successful_commit_disarms_database_rollback(self):
        commit = self.lower.index("servicetransactioncommitted := true;")
        tail = self.lower[commit:commit + 500]
        self.assertIn("databaseupgradeattempted := false;", tail)


if __name__ == "__main__":
    unittest.main()
