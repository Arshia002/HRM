# Test Report — HRM v0.3.0-alpha.1

Status: **Local source/package validation PASS; Windows acceptance pending GitHub Actions.**

## Local result

- 58/58 Unit + Integration + UI contract tests: PASS
- Packaging/Branding fail-fast contract: PASS
- Python compileall: PASS
- YAML/JSON parse: PASS
- SQLite integrity and 36-record Demo seed: PASS
- Native-only UI (no WebView/QtWebEngine): PASS
- Official company logo packaging: PASS
- Clean ZIP extraction + manifest SHA/size checks: PASS
- Clean Git tracking simulation: PASS

## Windows-specific acceptance

The workflow additionally runs the frozen `HRM.exe --ui-smoke-test`, which constructs the actual Login dialog and Dashboard shell without network I/O before Inno Setup is compiled. The remaining authoritative checks are Windows Service, UAC/ACL, actual Installer, Desktop shortcut, login/change-password, upgrade, data preservation and uninstall.

Success artifact: `HRM-0.3.0-alpha.1-Tested-Setup`.
