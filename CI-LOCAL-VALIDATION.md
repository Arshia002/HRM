# HRM v0.5.0-alpha.1 — Local Validation

Date: 2026-09-01

Before delivery of the full native v4.9 UI candidate:

- Full source Unit/Integration/UI/Migration suite: **must pass from a clean ZIP**
- Focused Enterprise migration suite: **27/27 PASS**
- Fresh isolated `.venv` dependency installation: **PASS**
- Exact clean-runner pins (`cryptography`, `openpyxl`, `xlrd`): **PASS**
- Source/build dependency pin consistency: **PASS**
- Packaging + branding contract: **PASS**
- PyInstaller spec outputs: **PASS** (`HRM.exe`, `HRMServer.exe`, `HRMService.exe`, `HRMMigration.exe`)
- Approved chart: **PASS** (536 fixed + 32 named = 568 total; page 16 = 24)
- SQLite handle close, bounded retry, verified backup and rollback: **PASS**
- Proven alpha.4 upgrade/service compatibility markers: **PASS**
- Workflow dependency order and failure-log retention: **PASS**
- Twelve native v4.9 reference pages and full-page frozen smoke: **PASS**
- Aggregate analytics privacy and owner-access protection: **PASS**
- Excel UI contract is Dry Run only: **PASS**
- Public-safe seed: **PASS** (36 synthetic/demo records; no private workbook or production database)
- `.venv`, mutable logs and cache exclusion from the ZIP: **PASS**
- Clean Git-index contract with `--require-git-tracked`: **PASS**

Windows-only acceptance (PyInstaller Windows binaries, frozen Qt UI construction, Inno Setup, SCM, UAC, ACL, Desktop shortcut, install/upgrade/uninstall) must still pass on GitHub `windows-2022`. Local validation intentionally does not substitute for that runner.
