# HRM v0.2.0-alpha.3 — Test Report

Date: 2026-08-28

## Root cause of the alpha.2 CI failure

The failure artifact from GitHub stopped in `Validate packaging contract` before PyInstaller or Inno Setup. `PACKAGE-MANIFEST.json` declared five local `.pytest_cache` files. Git ignored those files, therefore a clean GitHub checkout did not contain them and the contract correctly failed. See `ROOT-CAUSE-alpha2-ci.md`.

## Corrections in alpha.3

- Public CI package boundary is now selected from stable files only; `.pytest_cache`, `__pycache__`, virtualenv, coverage, build output and private/exported data are hard-excluded.
- `--require-git-tracked` proves every manifest path exists in Git's index before Windows CI starts.
- `HRMCentralService` is restored to remain compatible with the last proven `0.1.0-alpha.4` installer.
- Proven upgrade safety `service-stop-before-copy` is restored.
- Service identity is restored to `NT AUTHORITY\LocalService` with Service SID/ACL hardening.
- Synthetic seed is temporary-only during provisioning and is not persisted in Program Files.
- Frozen Qt client is smoke-tested with `HRM.exe --smoke-test` before Inno compilation.
- Windows build dependencies are pinned to the versions captured by the successful alpha.4 baseline.
- Bootstrap password `13811381`, forced password change and permanent invalidation after change remain covered by tests.
- Public seed remains 36 Synthetic/Demo records; real company data is absent.

## Local validation completed before delivery

- Source Unit/Integration tests: **52/52 PASS**
- Packaging contract: **PASS**
- PyInstaller output-name contract: **PASS** (`HRM.exe`, `HRMServer.exe`, `HRMService.exe`)
- Proven alpha.4 service/upgrade markers: **PASS**
- Python compileall: **PASS**
- GitHub Workflow YAML parse: **PASS**
- JSON parse: **PASS**
- SQLite `integrity_check`: **PASS**
- Public-data guard: **PASS** (36 demo personnel; no `data/export`, xls/xlsx/csv)
- Bootstrap/API forced-change flow: **PASS**
- TLS integration: **PASS**
- Multi-admin/concurrency tests: **PASS**
- Final ZIP clean-extract re-test: **PASS**
- Final ZIP clean Git index simulation with `--require-git-tracked`: **PASS**
- Manifest/ZIP check rejects transient cache paths: **PASS**

## Remaining authoritative gate

This environment cannot execute Windows Service Control Manager, Inno Setup/UAC or a Windows desktop session. GitHub `windows-2022` therefore remains the authoritative acceptance gate for:

`Contract -> PyInstaller 3 EXE -> Frozen Qt client smoke -> Frozen server smoke -> Inno Setup -> Clean Install -> HRMCentralService -> LocalService/SID/ACL -> TLS -> Desktop -> Bootstrap Login -> Forced Password Change -> Upgrade -> Data Preservation -> Uninstall`

Expected success artifact:

`HRM-0.2.0-alpha.3-Tested-Setup`

Failure artifact:

`HRM-0.2.0-alpha.3-Failure-Logs`
