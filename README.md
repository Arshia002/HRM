# HRM v0.4.0-alpha.3 — Clean Runner Enterprise Candidate

این Candidate روی چهار Baseline سبز قبلی ساخته شده است. هدف این Milestone اتصال کنترل‌شده چهار فایل خصوصی به بک‌اند Enterprise، با حفظ چارت تأییدشده ۵۶۸ پستی است.

## تغییرات اصلی

- تشخیص درست ۱۳۵۶ پرسنل از دو منبع اصلی بدون دوباره‌شماری برگه خلاصه.
- اعمال ۵۹۰ نگاشت تکمیلی واحد سازمانی از فایل شهرستان.
- حفظ ۵۳۶ پست ثابت، ۳۲ پست بانام، جمع ۵۶۸ و پست تأییدشده صفحه ۱۶.
- پیش‌آزمون تطبیق کامل شماره پرسنلی و کد پست با دیتابیس Enterprise.
- Backup همراه SHA-256، تراکنش یکپارچه، Audit batch و Rollback خودکار.
- ابزار مستقل `HRMMigration.exe` با پشتیبانی آفلاین `.xls` و `.xlsx`.
- حفظ کامل Service/TLS/ACL/Upgrade/Uninstall از Baseline سبز.
- عدم وجود دیتای واقعی در Git؛ Seed فقط 36 رکورد Demo/Synthetic است.

## اعمال روی Branch

ZIP را در Root همان Repository استخراج کنید و اجرا کنید:

```cmd
PUSH-TO-GITHUB.cmd
```

این دستور ابتدا محیط `.venv` مجزا می‌سازد، وابستگی‌های Pin‌شده را نصب و تست‌های محلی را اجرا می‌کند. فقط پس از PASS، Stage و Commit و Push انجام می‌شود:

```cmd
PUSH-TO-GITHUB.cmd
```

## Artifactها

- موفق: `HRM-0.4.0-alpha.3-Tested-Setup`
- ناموفق: `HRM-0.4.0-alpha.3-Failure-Logs`

این Candidate زمانی Windows-Tested است که Build + Frozen Migration Smoke + Inno Setup + Clean Install + Login + Service/TLS/ACL + Upgrade + Data Preservation + Uninstall در GitHub Actions سبز شوند.
