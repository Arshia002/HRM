# HRM v0.2.0-alpha.2 — Local Validation

تاریخ: 2026-08-27

نتیجه پیش از تحویل CI package:

- Packaging contract: **PASS**
- PyInstaller spec output contract: **PASS** (`HRM.exe`, `HRMServer.exe`, `HRMService.exe`)
- Inno source existence + ASCII-safe paths: **PASS**
- Version contract: **PASS** (`0.2.0-alpha.2`)
- Public-safe seed gate: **PASS** (36 رکورد synthetic، بدون داده واقعی)
- Unit/Integration tests: **41/41 PASS**
- Python compileall: **PASS**
- GitHub Workflow YAML parse: **PASS**
- JSON parse: **PASS**
- CI overlay manifest path safety: **PASS** (تمام pathهای اعلام‌شده بسته ASCII-safe)
- Regression with existing Persian-named repository docs: **PASS**

این Validation عمداً جای Windows CI را نمی‌گیرد. Build واقعی PyInstaller for Windows، Inno Setup، Service، TLS، ACL، Desktop Shortcut، Login، Upgrade و Uninstall باید روی GitHub `windows-2022` سبز شوند.
