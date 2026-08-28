# HRM v0.2.0-alpha.3 — Windows CI Build Fix Candidate

این بسته برای اصلاح Build ناموفق `v0.2.0-alpha.1` ساخته شده است. مشکل اصلی به‌صورت ریشه‌ای شناسایی شده: `client.spec` فایل `SazmanHR.exe` می‌ساخت ولی Builder و Installer منتظر `HRM.exe` بودند.

## تغییر اصلی

- خروجی Client: `HRM.exe`
- خروجی Server: `HRMServer.exe`
- خروجی Service: `HRMService.exe`
- Installer: `HRM-Setup-x64.exe`
- نسخه: `0.2.0-alpha.3`
- داده داخل Git: فقط 36 رکورد Demo/Synthetic
- رمز Bootstrap آزمایشی: `13811381` با تغییر اجباری در اولین ورود

## محافظ جدید Build

قبل از PyInstaller، فایل `ci/validate_package_contract.py` موارد زیر را بررسی می‌کند:

- نام خروجی هر سه فایل `.spec`
- وجود تمام Sourceهای Inno Setup
- ASCII-safe بودن مسیر Sourceهای Installer
- یکسان بودن Version در Backend/Installer/Smoke Test/Manifest
- نبود `data/export` و فایل‌های Excel واقعی
- سلامت Seed مصنوعی

اگر هر کدام ناسازگار باشد Build قبل از مرحله سنگین متوقف می‌شود.

## اعمال روی Branch فعلی

ZIP را روی ریشه Repository فعلی `feat/native-v49-shell` استخراج کنید و سپس:

```cmd
APPLY-ALPHA3-FIX.cmd
```

این فایل، فایل‌های منسوخ Candidate قبلی را از Git حذف می‌کند و Packaging Contract را اجرا می‌کند. بعد از PASS:

```cmd
git add -A
git commit -m "fix: repair HRM alpha.3 Windows packaging contract"
git push origin feat/native-v49-shell
```

GitHub Actions باید Artifactهای زیر را تولید کند:

- سبز: `HRM-0.2.0-alpha.3-Tested-Setup`
- قرمز: `HRM-0.2.0-alpha.3-Failure-Logs`

## Gate نهایی

Local/Linux validation جای Windows CI را نمی‌گیرد. نسخه زمانی Windows-Tested محسوب می‌شود که Build + Inno Setup + Clean Install + Service/TLS/ACL + Bootstrap Login + Forced Password Change + Upgrade + Data Preservation + Uninstall در GitHub Actions سبز شوند.
