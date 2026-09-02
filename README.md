# HRM v0.6.0-beta.1 — Protected Organizational Pilot Candidate

این Beta روی Tag تست‌شده `v0.5.0-alpha.1` و Commit `8e3eb3baecb46d2a0f964322584e668a6e926ce2` ساخته شده است. هدف، اعتبارسنجی چهار منبع واقعی سازمان روی Runner ویندوز GitHub پیش از هر نصب داخل سازمان است؛ داده خام وارد Git نمی‌شود و فقط بسته رمز‌شده احرازهویت‌شده Commit می‌شود.

## تغییرات اصلی

- حفظ کامل رابط Native دوازده‌صفحه‌ای v4.9 و Baseline سبز Installer/Service/TLS/ACL/Upgrade.
- رمزگذاری Authenticated چهار فایل پیش از Git با کلید جدا در GitHub Environment Secret.
- اجرای زنجیره واقعی `Decrypt -> Reconcile -> Staging -> Backup -> Apply -> Rollback -> Replay` در فضای موقت Runner.
- قرارداد قطعی ۱۳۵۶ پرسنل و ۵۳۶ پست ثابت + ۳۲ پست بانام = ۵۶۸؛ صفحه ۱۶ = ۲۴.
- پشتیبانی از گونه‌های پست بانام مانند «بانام ایثار» و جلوگیری از شمارش اشتباه آن‌ها به‌عنوان پست ثابت.
- Artifact و Log فقط Aggregate؛ بدون نام، کد ملی، شماره پرسنلی، فایل خام، دیتابیس خصوصی یا کلید.
- Seed عمومی همچنان فقط ۳۶ رکورد کاملاً مصنوعی است.

## ترتیب اجرای الزامی

ZIP را روی Root مخزن استخراج کنید. چهار فایل واقعی باید در یک پوشه خارج از مخزن باشند. سپس:

```cmd
PREPARE-REAL-DATA-V060B1.cmd "C:\HRM-Private-Input"
CONFIGURE-REAL-DATA-SECRET-V060B1.cmd
PUSH-TO-GITHUB.cmd
```

اسکریپت Push شاخه `feat/organizational-pilot-v060b1` را انتخاب می‌کند، تمام گیت‌های محلی را پیش از Stage اجرا می‌کند، کلید را از Git مسدود می‌کند و فقط بسته `.enc` و Sidecar آن را همراه کد می‌فرستد. GitHub تنها پس از عبور تست دیتای واقعی سراغ ساخت Installer می‌رود.

## Artifactها

- موفق: `HRM-0.6.0-beta.1-Tested-Setup`
- ناموفق: `HRM-0.6.0-beta.1-Failure-Logs`

این Candidate فقط زمانی قابل پایلوت است که تست دیتای واقعی، Build، Frozen Smoke، Inno Setup، نصب تمیز، Login، Service/TLS/ACL، Upgrade، حفظ داده و Uninstall همگی روی GitHub Actions سبز شوند.
