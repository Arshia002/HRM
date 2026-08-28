# HRM v0.2.0-alpha.2 — Test Report

## علت شکست alpha.1

`client.spec` خروجی را با نام `SazmanHR.exe` تولید می‌کرد اما Builder، Inno Setup و Acceptance Test همگی `HRM.exe` می‌خواستند. بنابراین PyInstaller عملاً موفق بود ولی Build contract در پایان به‌درستی با خطای missing `HRM.exe` متوقف شد.

یک خطای پنهان دوم نیز پیش از Build بعدی شناسایی شد: Source pathهای فارسی Inno با نام فایل‌های `#U...` حاصل از ZIP هم‌خوان نبودند. در alpha.2 تمام Source pathهای Installer به نام‌های ASCII-safe تبدیل شدند.

## اصلاحات پیشگیرانه

- `client.spec -> HRM.exe`
- `server.spec -> HRMServer.exe`
- `service.spec -> HRMService.exe`
- Installer script: `build/windows/HRM.iss`
- Preflight payload: `HRMServerPreflight.exe`
- Fail-fast: `ci/validate_package_contract.py`
- بررسی خروجی هر Spec بلافاصله بعد از PyInstaller
- inventory فایل‌های Frozen و PyInstaller warnings در Failure diagnostics
- Guard برای جلوگیری از ورود دیتای واقعی به Git

## تست‌های انجام‌شده قبل از تحویل

- Packaging contract: **PASS**
- Unit/Integration: **41/41 PASS**
- Python compileall: **PASS**
- YAML/JSON parse: **PASS**
- SQLite integrity + synthetic seed: **PASS**
- CI overlay manifest + Inno payload path safety: **PASS**
- Bootstrap `13811381` + forced password change + invalidation logic: **PASS در تست‌های Source/API**
- Shared multi-admin data/concurrency tests: **PASS**
- TLS integration test: **PASS**


## اصلاح pre-push در CI package revision 2

Gate اولیه alpha.2 به اشتباه کل working tree را برای نام فایل ASCII اسکن می‌کرد و به مستندات فارسی قدیمی Repository گیر می‌داد، با اینکه آن فایل‌ها جزو Installer یا CI overlay نبودند. Gate اصلاح شد تا مرز واقعی بسته را از `PACKAGE-MANIFEST.json` و Sourceهای `HRM.iss` بگیرد.

Regression simulation با همان نام‌های فارسی گزارش‌شده روی Repository انجام شد: **PASS**. Validator و کل 41 تست در حضور آن فایل‌ها نیز سبز شدند.

## Gate باقی‌مانده

این محیط Linux است؛ بنابراین فایل نهایی Windows-Tested فقط پس از سبزشدن GitHub Actions روی `windows-2022` تأیید می‌شود. CI باید این مسیر را کامل کند:

`Contract -> PyInstaller 3 EXE -> Frozen server smoke -> Inno Setup -> Clean Install -> HRMCentral -> TLS -> ACL -> Desktop -> Bootstrap Login -> Forced Password Change -> Upgrade -> Data Preservation -> Uninstall`

Artifact سبز مورد انتظار:

`HRM-0.2.0-alpha.2-Tested-Setup`
