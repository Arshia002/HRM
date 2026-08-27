# HRM v0.2.0-alpha.1 — Test Candidate Report

تاریخ بررسی: 2026-08-27

## نتیجه تست در محیط ساخت فعلی

- Unit/Integration tests: **35/35 PASS**
- Python compileall: **PASS**
- SQLite integrity_check: **ok**
- Seed personnel: **36 رکورد synthetic-demo**
- Organization chart pages: **53**
- Seed users/sessions: **0 کاربر اولیه داخل Seed**
- Bootstrap first-login: **13811381** فقط برای مالک اولیه نصب تازه؛ تغییر رمز اجباری و سپس رمز اولیه نامعتبر می‌شود.
- Native client: Qt/PySide6، بدون WebView/Browser engine.
- Windows product branding target: HRM / HRM-Setup-x64.exe / HRMCentral / C:\ProgramData\HRM-Kermanshah

## مواردی که عمداً در این Candidate انجام نشده

این محیط Linux است و Inno Setup، Windows Service، UAC، Desktop Shortcut و Windows ACL در آن قابل اجرای واقعی نیستند. بنابراین **این بسته Source Test Candidate است و Setup جدید Windows را نهایی اعلام نمی‌کند**. مرحله بعد، Windows CI/Windows x64 است که باید Build + Clean Install + Upgrade from alpha.4 + TLS + ACL + Service + Desktop + Uninstall را سبز کند.

## داده

برای جلوگیری از ورود داده واقعی پرسنلی در این مرحله، ۱۳۵۶ رکورد پرسنلی مرجع از Seed آزمایشی حذف و با ۳۶ رکورد صریحاً synthetic-demo جایگزین شده‌اند. ۵۳ صفحه ساختار چارت برای تست UI/ساختار باقی مانده است.

## آیکون

پکیج v4.9 فایل مستقل `app.ico` در اختیار نمی‌گذارد؛ فقط Installer موجود است. در این Candidate از آیکون سورس Enterprise با نام `HRM.ico` استفاده شده است. تطبیق دقیق آیکون 4.9 باید در Windows build بعدی با فایل اصلی یا استخراج معتبر resource انجام شود.
