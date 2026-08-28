# Test Report — HRM v0.3.0-alpha.2

Status: **Local source/package validation PASS; Windows acceptance pending GitHub Actions.**

## Local result

- 63/63 Unit + Integration + UI + Organization/Personnel tests: PASS
- Migration 6 (`organization_personnel_core`): PASS
- Personnel create/update/search/filter: PASS
- Unit/position/assignment projection: PASS
- Occupancy filters: PASS
- Optimistic concurrency conflict rejection: PASS
- Audit-chain after personnel edits: PASS
- Packaging/Branding fail-fast contract: PASS
- Python compileall: PASS
- YAML/JSON parse: PASS
- SQLite integrity and 36-record Demo seed: PASS
- Native-only UI (no WebView/QtWebEngine): PASS
- No real personnel export/Excel in package: PASS
- Clean ZIP extraction + manifest SHA/size checks: PASS
- Clean Git tracking simulation: PASS

## Windows-specific acceptance

GitHub Actions remains authoritative for the frozen executable, Windows Service, UAC/ACL, TLS, actual Installer, Desktop shortcut, Bootstrap/change-password path, Upgrade, data preservation and Uninstall.

Success artifact: `HRM-0.3.0-alpha.2-Tested-Setup`.
