# HRM v0.3.0-alpha.2 — Organization & Personnel Core

این نسخه روی Baseline سبز `HRM 0.3.0-alpha.1` ساخته شده و زیرساخت اثبات‌شده Windows را حفظ می‌کند.

## هدف این Build

- اضافه شدن هسته واقعی پرسنل و ساختار سازمانی به Backend Enterprise 16.0.7.
- حفظ قالب Native Qt و زبان بصری SazmanHR v4.9 از Build قبلی.
- صفحات Native برای پرسنل، واحدهای سازمانی و پست‌های سازمانی.
- جستجو و فیلتر پرسنل بر اساس نام/شماره، واحد، گروه استخدامی، وضعیت و محل خدمت.
- پروفایل پرسنلی و نمایش ارتباط فرد با واحد و پست نرمال‌شده.
- مدل نرمال‌شده `organizational_units`، `positions` و `personnel_assignments` با Migration نسخه 6.
- کنترل همزمانی با `row_version` و Audit برای تغییرات پرسنلی.
- آماده‌سازی schema مربوط به Import Batch در حالت dry-run؛ داده واقعی هنوز وارد Git یا Seed نمی‌شود.
- Seed این Candidate فقط Synthetic/Demo است.

## مواردی که نباید Regression کنند

- Native Qt UI و Branding سبز `0.3.0-alpha.1`
- Windows Service: `HRMCentralService`
- Service account: `NT AUTHORITY\\LocalService`
- TLS / ACL / Firewall
- Bootstrap اولیه `13811381` و Change Password اجباری
- Upgrade و حفظ Data Directory
- Uninstall با حفظ داده
- Server / Client / Full installer modes

## Acceptance اصلی

پس از نصب و ورود، کاربر باید بتواند از Dashboard وارد صفحات پرسنل و ساختار سازمانی شود، افراد Demo را جستجو و فیلتر کند، پروفایل فرد را ببیند و واحد/پست متصل به او را مشاهده کند.
