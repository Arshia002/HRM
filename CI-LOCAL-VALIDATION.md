# HRM v0.6.0-beta.1 — Local Validation

Date: 2026-09-02

Before delivery of the protected organizational pilot candidate:

- Full source Unit/Integration/UI/Migration suite: **114/114 PASS locally; must repeat from a clean ZIP**
- Focused Enterprise migration suite: **28/28 PASS**
- Fresh isolated `.venv` dependency installation: **enforced by APPLY/GitHub; current sandbox network unavailable**
- Exact clean-runner pins (`cryptography`, `openpyxl`, `xlrd`): **static parity PASS; runtime install must repeat on Windows**
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
- Authenticated encrypted-bundle round trip, wrong-key and tamper rejection: **PASS**
- Exact-scale synthetic 1356-person/568-post apply/rollback/replay: **PASS**
- Real-data artifact privacy boundary: **PASS** (aggregate-only)

The exact 1356-person/568-post contract and Windows-only acceptance must pass on GitHub `windows-2022` after the user prepares the encrypted four-source bundle. Local synthetic validation intentionally does not claim that the private source content has passed.
