# Changelog

## 0.4.0-alpha.2

- اتصال guarded چهار فایل خصوصی به دیتابیس Enterprise generation 16.
- تثبیت قرارداد تأییدشده چارت روی ۵۳۶ ثابت + ۳۲ بانام = ۵۶۸ و حفظ پست صفحه ۱۶.
- حذف ۵۹۰ duplicate کاذب با شناسایی فایل شهرستان به‌عنوان enrichment.
- انتخاب خودکار برگه کامل فایل شرکتی و جلوگیری از دوباره‌شماری برگه خلاصه.
- افزودن Backup سلامت‌سنجی‌شده، SHA-256، تراکنش اتمیک، Audit batch و Rollback خودکار.
- افزودن `HRMMigration.exe` آفلاین با readerهای pinشده `openpyxl` و `xlrd`.
- افزودن تست واقعی محلی روی ۱۳۵۶ پرسنل و تست‌های مصنوعی بدون انتشار PII در Git.
- بستن صریح اتصال‌های مستقیم SQLite در تست‌های مهاجرت برای جلوگیری از قفل `hrm.sqlite` و `WinError 32` روی Windows.

## 0.3.0-alpha.2

- اولین Native UI milestone روی Baseline سبز `0.2.0-alpha.3`.
- بازطراحی Login بومی Qt با RTL، پنل برند و نمایش رسمی HRM.
- افزودن Sidebar سمت راست، Header مدیریتی، وضعیت اتصال و کارت کاربر.
- بهینه‌سازی Dashboard cards برای نمای سازمانی 1366×768 و 1920×1080.
- استفاده از لوگوی سازمانی به‌عنوان HRM application/installer branding asset.
- افزودن Frozen `--ui-smoke-test` قبل از Inno Setup برای ساخت واقعی Login و Dashboard shell در Windows CI.
- افزودن Contract مستقل UI/Branding و Regression tests بدون WebView/QtWebEngine.
- حفظ بدون تغییر Baseline سرویس `HRMCentralService`، LocalService، TLS، ACL، Upgrade و Data Preservation.
- حفظ Bootstrap قدیمی و Forced Password Change (رمز ثابت در alpha.2 بازنشسته شد).

## 0.2.0-alpha.3

- رفع Root Cause Failure نسخه alpha.2: حذف `.pytest_cache` و تمام فایل‌های transient از Manifest/CI overlay.
- افزودن clean-checkout gate با `--require-git-tracked` تا Manifest فقط فایل‌های واقعاً قابل بازسازی از Git را بپذیرد.
- حفظ اصلاح نام خروجی PyInstaller: `client.spec -> HRM.exe`.
- بازگردانی `HRMCentralService` برای سازگاری Upgrade با baseline سبز `0.1.0-alpha.4`.
- بازگردانی `service-stop-before-copy` پیش از جایگزینی فایل‌های سرویس در Upgrade.
- بازگردانی حساب کم‌اختیار `NT AUTHORITY\LocalService`، Service SID و ACL اثبات‌شده alpha.4.
- بازگردانی Frozen Qt client smoke test پیش از Inno Setup.
- عدم persist شدن synthetic seed در Program Files؛ seed فقط موقت در provisioning.
- Pin شدن dependencyهای Windows build به snapshot baseline سبز alpha.4.
- حفظ Bootstrap قدیمی + تغییر اجباری رمز + ابطال دائمی رمز اولیه.
- حفظ Guard دیتای عمومی: فقط Seed مصنوعی 36 رکوردی و بدون داده واقعی شرکت.

# تغییرات

## 16.0.7 Proven Health Path and Durable Diagnostics

- بازگردانی TLS health سبک و اثبات‌شده نسخه 16.0.5 برای جلوگیری از اجرای integrity check در هر درخواست health
- حفظ حذف آزمون مستقیم `--verify-database` از حساب غیرسرویسی پس از سخت‌سازی ACL
- ثبت START/PASS/FAIL هر مرحله provisioning داخل لاگ رسمی Inno Setup
- انتقال محتوای خطای محافظت‌شده سرویس به لاگ رسمی Setup توسط همان فرایند elevated
- بستن Transcript پیش از جمع‌آوری ProgramData و جلوگیری از گم‌شدن لاگ هنگام PermissionError
- ذخیره مستقل وضعیت Service، ACL، خلاصه Exception و فهرست فایل‌های تشخیصی در هر اجرای Windows
- فراخوانی stop سرویس با timeout هنگام Uninstall

## 16.0.6 Service-Owned Database Health Fix

- حذف آزمون مستقیم فایل‌های محافظت‌شده ProgramData با حساب GitHub Runner
- اجرای `PRAGMA quick_check` داخل Windows Service، یعنی با همان هویتی که مالک دیتابیس است
- افزودن وضعیت integrity و schema دیتابیس به پاسخ TLS health بدون افشای محتوای سازمانی
- حفظ ACL سخت‌گیرانه نسخه 16.0.5 و جلوگیری از اعطای دسترسی به حساب‌های عادی
- افزودن تست رگرسیون برای جلوگیری از بازگشت `--verify-database` پس از سخت‌سازی ACL

## 16.0.5 Windows Service ACL Fix

- بازگردانی حساب کم‌اختیار Windows Service به NT AUTHORITY\LocalService مطابق baseline تأییدشده alpha.4
- فعال‌سازی Service SID اختصاصی `SazmanHREnterpriseCentral`
- اعطای Modify مستقیم به `NT SERVICE\SazmanHREnterpriseCentral` پیش از شروع سرویس
- حذف `/C` از `icacls` تا هیچ خطای ACL نادیده نماند
- اعمال ACL در دو مرحله: اثبات سلامت سرویس، سپس حذف ارث‌بری و آزمون نهایی TLS
- ثبت `service-config.txt` و `data-acl.txt` در هر نتیجه آزمون Windows
- کنترل خودکار حساب سرویس و ACE مؤثر Service SID

## 16.0.4 Silent Setup Deadlock Fix

- جایگزینی پیام‌های `MsgBox` با `SuppressibleMsgBox` تا نصب بدون‌صفحه منتظر کلیک نماند
- افزودن timeout مستقل برای نصب، اعتبارسنجی دیتابیس و حذف آزمایشی
- تولید لاگ مستقل Inno Setup و جمع‌آوری لاگ‌های provisioning در صورت خطا
- افزودن تست رگرسی برای جلوگیری از بازگشت پنجره نامرئی در CI

## 16.0.3 Windows UTF-8 Build Fix

- رفع `UnicodeEncodeError` کنسول Windows هنگام چاپ نام فایل‌های فارسی توسط Inno Setup
- حفظ گزارش اصلی build با UTF-8 و تبدیل امن فقط برای نمایش کنسول‌های قدیمی
- اجبار `PYTHONUTF8` و `PYTHONIOENCODING` در CI ویندوز
- ارتقای checkout، setup-python و upload-artifact به نسخه‌های مبتنی بر Node.js 24
- افزودن تست رگرسیون شبیه‌ساز کنسول cp1252 با مسیر فارسی

## 16.0.2 Windows Log Handle Fix

- بستن و جداکردن صریح `RotatingFileHandler` در تمام مسیرهای موفق و خطای سرور
- جلوگیری از بازماندن `logs\\server.jsonl` پس از init، verify و provisioning test
- بستن handlerهای قبلی پیش از پیکربندی مجدد logger
- افزودن آزمون حذف واقعی فایل لاگ پس از پایان هر اجرای سرور

## 16.0.1 Windows Builder Cleanup Fix

- بستن صریح اتصال SQLite بررسی هویت دیتابیس؛ context manager استاندارد SQLite فایل را نمی‌بندد
- رفع خطای Windows `NotADirectoryError` هنگام پاک‌سازی دیتابیس‌های موقت آزمون
- بستن صریح اتصال‌های SQLite در آزمون دیتابیس ناسازگار
- حفظ همه کنترل‌های استقلال Setup، جداسازی نسل ۱۶ و fail-fast نصب

## 16.0.0 Isolated Offline Installer

- AppId، مسیر نصب، ProgramData، دیتابیس، تنظیمات کلاینت و Windows Service کاملاً جدید
- مسدودسازی دیتابیس قدیمی یا ناسازگار پیش از هرگونه اجرای schema یا migration
- مسیر داده جدید `C:\ProgramData\SazmanHR-Enterprise` و دیتابیس `enterprise.sqlite`
- سرویس جدید `SazmanHREnterpriseCentral` بدون برخورد با سرویس نسل‌های قبلی
- توقف نصب هنگام شکست init، ACL، Service، Firewall یا TLS health
- ثبت traceback نصب مخفی در `logs\setup-server.log`
- اجرای frozen server smoke test پیش از ساخت Setup
- اثبات خودکار عدم تغییر مسیر قدیمی در Windows CI
- Setup مقصد کاملاً آفلاین و بدون نیاز به Python، Qt، pip، PowerShell، winget، مرورگر یا اینترنت

## 15.2.0 Windows SQLite Fix

- بستن قطعی handle تمام اتصال‌های SQLite پس از پایان context برای Windows
- رفع WinError 32 هنگام پاک‌سازی آزمون، بازیابی دیتابیس و جایگزینی فایل
- بستن اتصال‌های موقت integrity check، backup و safety copy
- خارج‌کردن `build-output` و محیط venv از آزمون پاکی سورس
- افزودن آزمون بسته‌شدن واقعی اتصال دیتابیس

## 15.1.0 Windows Builder Fix

- حذف وابستگی لانچر یک‌کلیکی به PowerShell برای سازگاری با policy سازمانی
- سازنده بومی Python برای آزمون، PyInstaller، Inno Setup، checksum و اجرای Setup
- تشخیص پوشه غیرقابل‌نوشتن و جلوگیری از اجرای مستقیم داخل ZIP/Program Files
- لاگ پایدار `build-setup-bootstrap.log` و `build-output\build.log`
- پیام خطای مرحله‌ای برای نبود Python، winget، Inno Setup یا قفل فایل‌ها
- حفظ پنجره فرمان پس از موفقیت یا خطا تا تأیید کاربر

## 15.0.0 Windows Test Candidate

- انتقال کامل رابط از Tk به کلاینت بومی Qt
- TLS پیش‌فرض، گواهی خودکار و pinning اثرانگشت
- migration ترتیبی با checksum و schema نسخه ۵
- پشتیبان خودکار، retention، integrity check و بازیابی آفلاین
- لاگ عملیاتی JSON و داشبورد monitoring
- ریزدسترسی کاربر روی RBAC
- MFA مبتنی بر TOTP و کدهای بازیابی یک‌بارمصرف
- گردش کار و اعلان‌های داخلی
- آزمون شبکه پنج مدیر و کنترل تعارض هم‌زمان
- Windows CI برای build، نصب silent، Service و TLS health
- bootstrap یک‌کلیکی برای ساخت Setup روی Windows

## خط مبنا Clean

- دیتاست پاک‌سازی‌شده ۱۳۵۶ پرسنل و ۵۳ صفحه چارت
- هیچ باینری، runtime، سرویس یا حساب کاربری از بسته‌های خراب قبلی وارد پروژه نشده است

## 0.2.0-alpha.3 CI package revision 2
- Corrected the pre-push ASCII-path validator to inspect the CI overlay manifest and Inno payload, not unrelated files already present in the repository.
- Added regression coverage for pre-existing Persian-named documentation.
