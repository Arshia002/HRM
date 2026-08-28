# HRM v0.3.0-alpha.1 — Test Report

Date: 2026-08-28

## Milestone scope

This candidate starts from the Windows-tested `0.2.0-alpha.3` baseline. The security/network/installer path is preserved; the feature change is the Native Qt user interface and HRM branding.

## UI / Branding changes covered

- Native RTL Login shell with HRM/company branding.
- Native right-side Sidebar and management Header.
- Connection status badge and signed-in user panel.
- Dashboard stat-card layout.
- Official company logo bundled into the frozen client and Windows icon/Setup branding.
- Native UI geometry targets suitable for 1366×768 and 1920×1080.
- No browser, WebView or QtWebEngine dependency.
- Frozen `HRM.exe --ui-smoke-test` executes before Inno Setup compilation.

## Regression guarantees retained

- `HRMCentralService` service identity and upgrade compatibility.
- `NT AUTHORITY\LocalService`, Service SID and hardened ACL path.
- TLS and Firewall provisioning.
- Bootstrap password `13811381`, forced password change and permanent Bootstrap invalidation.
- In-place Upgrade and data-preservation acceptance path.
- Full / Server / Client installer modes.
- Public repository contains only a 36-record Synthetic/Demo seed.

## Local validation completed before delivery

- Source Unit/Integration/UI tests: **58/58 PASS**
- Packaging/Branding contract: **PASS**
- PyInstaller output-name contract: **PASS**
- Python compileall: **PASS**
- Workflow YAML + JSON parse: **PASS**
- SQLite `integrity_check`: **PASS**
- Public-data guard: **PASS**
- Bootstrap/API forced-change flow: **PASS**
- TLS integration: **PASS**
- Multi-admin/concurrency: **PASS**
- Release builder excludes mutable `.log`, cache and generated worktree files: **PASS**
- Final ZIP clean extraction: **PASS**
- Final ZIP clean Git tracking contract: **PASS**

## Authoritative Windows gate

GitHub `windows-2022` must prove:

`Contract -> 58 tests -> PyInstaller 3 EXE -> Frozen Qt smoke -> Frozen Native UI smoke -> Frozen Server smoke -> Inno Setup -> Clean Install -> HRMCentralService -> LocalService/SID/ACL -> TLS -> Desktop Shortcut -> Bootstrap Login -> Forced Password Change -> Upgrade -> Data Preservation -> Uninstall`

Expected success artifact: `HRM-0.3.0-alpha.1-Tested-Setup`.

Failure artifact: `HRM-0.3.0-alpha.1-Failure-Logs`.
