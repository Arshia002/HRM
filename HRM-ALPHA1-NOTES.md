# HRM v0.2.0-alpha.1 — Test Candidate

این نسخه بر پایه سورس SazmanHR Enterprise 16.0.7 ساخته شده و هدف آن تثبیت هویت HRM، ورود اولیه و پوسته Native Qt است.

## تغییرات اصلی
- برندینگ کاربرمحور HRM در Client/Installer/Service
- رمز Bootstrap نصب تازه: `13811381` با مسیر هش جداگانه؛ سیاست رمز عادی ضعیف نشده است
- تغییر اجباری رمز در اولین ورود و حذف FIRST_LOGIN پس از تغییر
- نام خروجی مورد انتظار Windows: `HRM-Setup-x64.exe`
- نام سرویس: `HRMCentral` و داده عملیاتی: `C:\ProgramData\HRM-Kermanshah`
- حفظ معماری Native Qt، TLS، Audit، row_version، Backup و Server/Client/Full

## محدودیت این بسته
این محیط Linux است و Inno Setup/Windows Service را اجرا نمی‌کند. بنابراین این ZIP «Source Test Candidate» است؛ Setup نهایی فقط پس از Windows CI و smoke-install سبز باید تأیید شود.

## آیکون
پکیج v4.9 فقط Installer را شامل می‌کند و فایل app.ico مستقل ندارد. در این Candidate از آیکون سورس Enterprise به نام HRM.ico استفاده شده است. برای تطبیق پیکسلی با 4.9 باید app.ico اصلی یا استخراج معتبر آن در Windows build جایگزین شود.
