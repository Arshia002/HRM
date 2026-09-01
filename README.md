# HRM v0.5.0-alpha.1 — Full Native v4.9 UI Candidate

این Candidate روی Baseline تست‌شده `v0.4.0-alpha.3` ساخته شده است. هدف این Milestone پیاده‌سازی همه صفحه‌های مرجع v4.9 به‌صورت Native روی بک‌اند امن Enterprise، بدون تغییر پرریسک در مسیر نصب، سرویس، TLS، ACL، Upgrade و مهاجرت داده است.

## تغییرات اصلی

- دوازده صفحه مرجع v4.9 شامل چارت، وضعیت چارت، فهرست پرسنل، تحصیلات، وضعیت، سن، گزارش‌ها، Excel، کاربران، سوابق/پشتیبان، سلامت و تنظیمات.
- حفظ داشبورد، واحدها و پست‌ها، گردش کار و اعلان‌های Enterprise.
- جست‌وجوی سراسری، ناوبری RTL و نمایش صفحه‌ها بر اساس دسترسی واقعی Server.
- API تحلیلی Aggregate-only؛ هیچ شناسه، پروفایل خام یا اطلاعات فردی در پاسخ داشبورد منتشر نمی‌شود.
- Dry Run امن Excel داخل UI؛ اعمال Production همچنان فقط از مسیر گاردشده مدیر سیستم انجام می‌شود.
- جلوگیری Server-side از محدودسازی دسترسی مالک اصلی.
- ساخت و Refresh تمام صفحه‌های Native در Frozen UI Smoke پیش از Inno Setup.
- حفظ قرارداد ۱۳۵۶ پرسنل و چارت ۵۳۶ ثابت + ۳۲ بانام = ۵۶۸ برای مرحله داده واقعی.
- عدم وجود دیتای واقعی در Git؛ Seed فقط 36 رکورد Demo/Synthetic است.

## اعمال روی Branch

ZIP را در Root همان Repository استخراج کنید و اجرا کنید:

```cmd
PUSH-TO-GITHUB.cmd
```

این دستور Branch `feat/full-v49-ui-v050a1` را انتخاب می‌کند، محیط `.venv` مجزا می‌سازد، وابستگی‌های Pin‌شده و تمام تست‌های Privacy/UI/API/Migration/Package را اجرا می‌کند و فقط پس از PASS، Stage و Commit و Push انجام می‌دهد.

## Artifactها

- موفق: `HRM-0.5.0-alpha.1-Tested-Setup`
- ناموفق: `HRM-0.5.0-alpha.1-Failure-Logs`

این Candidate زمانی Windows-Tested است که Build + Frozen Migration Smoke + Inno Setup + Clean Install + Login + Service/TLS/ACL + Upgrade + Data Preservation + Uninstall در GitHub Actions سبز شوند.
