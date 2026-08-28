# HRM v0.2.0-alpha.3 — Local Validation

Date: 2026-08-28

Before delivery of this CI overlay:

- Source Unit/Integration: **52/52 PASS**
- Packaging contract: **PASS**
- Spec outputs: **PASS** (`HRM.exe`, `HRMServer.exe`, `HRMService.exe`)
- Proven alpha.4 upgrade/service compatibility markers: **PASS**
- Python compileall: **PASS**
- Workflow YAML + JSON parse: **PASS**
- SQLite integrity: **PASS**
- Public-safe seed: **PASS** (36 Synthetic/Demo records, no real personnel/export spreadsheets)
- Cache/ephemeral path exclusion: **PASS**
- Clean extracted ZIP unit/contract re-test: **PASS**
- Clean Git-index simulation with `--require-git-tracked`: **PASS**

Windows-only acceptance (PyInstaller Windows binaries, Inno Setup, SCM, UAC, ACL, Desktop shortcut, install/upgrade/uninstall) must still pass on GitHub `windows-2022`; this local validation does not falsely substitute for that runner.
