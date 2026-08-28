# راهنمای CI — HRM v0.2.0-alpha.3

این بسته اصلاح ریشه‌ای Failure نسخه `0.2.0-alpha.2` است. علت Failure قبلی ثبت شدن فایل‌های محلی `.pytest_cache` در `PACKAGE-MANIFEST.json` بود؛ فایل‌هایی که Git عمداً Track نمی‌کند و بنابراین در clean checkout گیت‌هاب وجود نداشتند.

## روش اعمال

1. روی Branch `feat/native-v49-shell` بمانید.
2. ZIP را در Root Repository استخراج کنید.
3. `APPLY-ALPHA3-FIX.cmd` را اجرا کنید؛ Contract + compile + unit/integration باید PASS شوند.
4. سپس `git add -A` بزنید.
5. قبل از Commit حتماً `python ci\validate_package_contract.py --require-git-tracked` را اجرا کنید.
6. Commit/Push کنید یا `PUSH-TO-GITHUB.cmd` را اجرا کنید.
7. اگر GitHub سبز شد Artifact `HRM-0.2.0-alpha.3-Tested-Setup` را دانلود کنید.
8. اگر قرمز شد Artifact `HRM-0.2.0-alpha.3-Failure-Logs` را برای بررسی نگه دارید.

## Windows acceptance path

Build سه EXE -> Frozen Qt smoke -> Frozen server smoke -> Inno Setup -> Clean Install -> `HRMCentralService` -> `NT AUTHORITY\LocalService` + SID/ACL -> TLS -> Desktop Shortcut -> ورود `13811381` -> تغییر اجباری رمز -> ابطال Bootstrap -> Upgrade -> حفظ داده -> Uninstall.

دیتای واقعی شرکت در این CI package وجود ندارد؛ Seed فقط 36 رکورد Synthetic/Demo دارد.
