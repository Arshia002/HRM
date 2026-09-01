# HRM v0.4.0-alpha.2 — اتصال امن داده واقعی به Enterprise

## قرارداد قطعی این نسخه

- بک‌اند هدف: دیتابیس سازگار با Enterprise generation 16
- پرسنل مورد انتظار: ۱۳۵۶ رکورد با ۱۳۵۶ شماره پرسنلی یکتا
- چارت مرجع: صفحه ۱ با ۵۳۶ پست ثابت، ۳۲ پست بانام و جمع ۵۶۸
- صفحه ۱۶: ۲۴ پست؛ پست اضافه تأییدشده حفظ می‌شود
- اطلاعات واقعی و خروجی‌های خصوصی نباید وارد Git شوند

## قواعد چهار فایل خصوصی

1. `اکسل رسمی.xls` و `اکسل شرکتی - حجمی - پیمانکاری.xls` جمعیت اصلی‌اند.
2. از فایل چندبرگه شرکتی، کامل‌ترین برگه انتخاب می‌شود و برگه خلاصه دوباره شمرده نمی‌شود.
3. `شهرستان.xls` جمعیت جدید نیست. برگه تکراری کنار گذاشته و نگاشت ۵۹۰ واحد سازمانی اعمال می‌شود.
4. انواع `بانام` و `بانام ایثار` حفظ می‌شوند.
5. ردیف قدیمی با نوع `0` وارد داده فعال نمی‌شود و در گزارش هشدار باقی می‌ماند.
6. کد ملی فقط برای کنترل تعارض در محیط خصوصی خوانده می‌شود و در گزارش عمومی نمایش داده نمی‌شود.

## Dry Run و کنترل دیتابیس هدف

در CMD مدیر سیستم:

```bat
HRMMigration.exe ^
  --input-dir "D:\HRM-Private-Data" ^
  --output-dir "D:\HRM-Migration-Output" ^
  --expected-personnel 1356 ^
  --target-db "%ProgramData%\HRM-Kermanshah\hrm.sqlite" ^
  --expected-chart-fixed 536 ^
  --expected-chart-named 32 ^
  --expected-chart-total 568
```

خروجی مجاز برای ادامه:

- `errors = 0`
- `persons = 1356`
- `enrichment_applied = 590`
- `approved_total_posts = 568`
- `integrity = ok`

دو هشدار شناخته‌شده، اعمال را مسدود نمی‌کنند: سابقه مشترک یک فرد در دو منبع استخدام و ردیف قدیمی نوع صفر.

## اعمال روی دیتابیس Enterprise

سرویس مرکزی باید هنگام اعمال متوقف باشد. ابتدا Dry Run را اجرا کنید. سپس:

```bat
HRMMigration.exe ^
  --input-dir "D:\HRM-Private-Data" ^
  --output-dir "D:\HRM-Migration-Output" ^
  --expected-personnel 1356 ^
  --apply-to-db "%ProgramData%\HRM-Kermanshah\hrm.sqlite" ^
  --backup-dir "D:\HRM-Private-Backup" ^
  --confirm-apply APPLY-TO-HRM ^
  --expected-chart-fixed 536 ^
  --expected-chart-named 32 ^
  --expected-chart-total 568
```

قبل از اولین تغییر یک Backup سلامت‌سنجی‌شده همراه SHA-256 ساخته می‌شود. اعمال در یک تراکنش انجام می‌شود. در خطای زمان اجرا، Backup به‌صورت خودکار بازگردانده می‌شود.

این نسخه هیچ رکورد پرسنلی را حدس نمی‌زند: مجموعه شماره‌های پرسنلی فایل‌ها باید دقیقاً با دیتابیس Enterprise برابر باشد. چارت، کاربران، نشست‌ها و زنجیره ممیزی حذف یا بازسازی نمی‌شوند.

## اجرای یک‌مرحله‌ای با CMD

از ریشه بسته توسعه، CMD زیر را با دسترسی Administrator اجرا کنید:

```bat
RUN-MIGRATION-V040A2.cmd "D:\HRM-Private-Data" "D:\HRM-Migration-Output" "D:\HRM-Private-Backup"
```

اسکریپت ابتدا Dry Run می‌گیرد، تأیید صریح درخواست می‌کند، سرویس را متوقف می‌کند، مهاجرت را اجرا و وضعیت قبلی سرویس را برمی‌گرداند.
