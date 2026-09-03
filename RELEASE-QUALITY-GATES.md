# HRM v0.7.0-rc.1 ci.2 Release Quality Gates

1. Immutable baseline: `v0.6.0-beta.1` / `a8b93c981603c58d0edaf3d999e088c7a674aa1b`.
2. Exact RC identity: application `0.7.0-rc.1`, package `0.7.0-rc.1-ci.4`, branch `feat/organizational-pilot-v070rc1`.
3. Package manifest SHA-256/byte integrity before overlay copy and again after install.
4. Full regression suite plus RC-focused TLS concurrency, disconnect/reconnect, DR and diagnostics privacy tests.
5. Protected real-data validation reuses the already-approved v060b1 encrypted bundle and `HRM_REAL_DATA_KEY`; plaintext never enters Git or artifacts.
6. Real-data contract stays fixed: 1356 personnel, 590 enrichments, 185 active named assignments, 1 ignored legacy row; approved chart 536+32=568, page 16=24.
7. Windows build must create HRM.exe, HRMServer.exe, HRMService.exe and HRMMigration.exe, then compile HRM-Setup-x64.exe.
8. Clean Windows install must prove TLS, LocalService, Service SID ACL, bootstrap login, forced password change, same-version in-place upgrade and uninstall preservation.
9. A second acceptance sequence must build the immutable beta tag and prove actual `v0.6.0-beta.1 -> v0.7.0-rc.1` Installer upgrade with data and credential preservation.
10. Diagnostics must exclude the database, FIRST_LOGIN, passwords, raw client IPs, raw HTTP detail and exception traces.
11. No tag or merge to main until the full GitHub run is green and its tested artifact hash is recorded.
