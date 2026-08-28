# HRM v0.3.0-alpha.1 — Local Validation

Date: 2026-08-28

Before delivery of this CI overlay:

- Source Unit/Integration/UI contract tests: **58/58 PASS**
- Packaging + Branding contract: **PASS**
- PyInstaller spec outputs: **PASS** (`HRM.exe`, `HRMServer.exe`, `HRMService.exe`)
- Frozen native UI smoke command wired before Inno: **PASS**
- Proven alpha.4 upgrade/service compatibility markers: **PASS**
- Python compileall: **PASS**
- Workflow YAML + JSON parse: **PASS**
- SQLite integrity: **PASS**
- Public-safe seed: **PASS** (36 Synthetic/Demo records, no real personnel/export spreadsheets)
- Mutable local `.log` / cache exclusion from CI overlay: **PASS**
- Native-only guard (no QtWebEngine/WebView): **PASS**
- Official HRM/company branding assets bundled: **PASS**
- Clean extracted ZIP contract/unit re-test: **PASS**
- Clean Git-index/clone simulation with `--require-git-tracked`: **PASS**

Windows-only acceptance (PyInstaller Windows binaries, frozen Qt UI construction, Inno Setup, SCM, UAC, ACL, Desktop shortcut, install/upgrade/uninstall) must still pass on GitHub `windows-2022`. Local validation intentionally does not substitute for that runner.
