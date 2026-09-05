# HRM v1.0.0-rc.1 Release Quality Gates

1. Tested baseline source is commit `8f1adfa88a1b53db1b075504c58900957e812894` (`v0.8.0-rc.1` tested source).
2. Exact final-candidate identity: application `1.0.0-rc.1`, package `1.0.0-rc.1-ci.2`, branch `release/v1.0.0-rc.1`.
3. Package manifest SHA-256/byte integrity is checked before overlay copy and again after installation.
4. Full regression suite, migration suite, six-client pinned-TLS, reconnect, certificate mismatch, disaster recovery and diagnostics privacy must pass.
5. Protected real-data validation reuses the approved v060b1 encrypted bundle and `HRM_REAL_DATA_KEY`; plaintext/key material never enters GitHub artifacts.
6. Real-data contract remains fixed: 1356 personnel, 590 enrichments, 185 active named assignments, 1 ignored legacy row; approved chart 536+32=568, page 16=24.
7. Personnel organization/position/location/status changes must use movement history; direct organizational overwrite is blocked.
8. Production RBAC profile is 2 Super Admin (`owner`) + 4 HR Admin (`admin`); Restore, hard delete, user/security administration and movement reversal are Super-Admin-only.
9. Scheduled backup defaults to every 24 hours with 30 local copies; a configurable verified secondary destination is supported and must be configured/restore-tested before production approval.
10. Windows build creates HRM.exe, HRMServer.exe, HRMService.exe and HRMMigration.exe, then compiles `HRM-Setup-x64.exe`.
11. Clean Windows installation proves TLS, LocalService, Service SID ACL, bootstrap login, forced password change, data preservation and uninstall preservation.
12. A separate acceptance sequence builds the exact tested v0.8 source and proves real `v0.8.0-rc.1 -> v1.0.0-rc.1` installer upgrade with service, TLS, database and credential preservation.
13. Linux Web Test remains explicitly `NOT FOR PRODUCTION`, Dockerized, same-core and localhost-bound by default.
14. Diagnostics exclude database contents, FIRST_LOGIN, passwords, raw client IPs, HTTP details, exception traces and the configured secondary backup path.
15. The Windows build supports optional Authenticode signing via a protected signing thumbprint; signing status is recorded in the CI manifest.
16. Generated test logs/temporary editor artifacts are excluded from final repository/package hygiene.
17. No `v1.0.0` production tag until the GitHub run is green, artifact SHA-256 is recorded, and the real 1-server + 6-client organizational pilot has no Critical Bug, Data Loss or Security Blocker.
