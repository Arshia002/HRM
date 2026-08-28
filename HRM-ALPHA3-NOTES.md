# HRM v0.2.0-alpha.3

این Build اصلاحی برای Windows CI است. تمرکز آن روی **reproducible clean-checkout packaging** و حفظ baseline تأییدشده `alpha.4` است.

اصلاحات کلیدی:

- حذف کامل `.pytest_cache` و سایر فایل‌های محلی/موقتی از مرز CI package و Manifest.
- Gate جدید `--require-git-tracked`: هر فایل Manifest باید واقعاً در Git index باشد تا clean checkout همان فایل‌ها را داشته باشد.
- بازگردانی نام سرویس `HRMCentralService` برای سازگاری Upgrade با `0.1.0-alpha.4`.
- بازگردانی توقف سرویس **قبل از جایگزینی فایل‌ها** (`service-stop-before-copy`).
- بازگردانی حساب کم‌اختیار `NT AUTHORITY\LocalService` و Service SID/ACL تأییدشده.
- عدم نگهداری seed آزمایشی در Program Files؛ seed فقط موقت برای provisioning استخراج می‌شود.
- Smoke test واقعی کلاینت Qt منجمدشده (`HRM.exe --smoke-test`) قبل از ساخت Installer.
- Dependencyهای Windows build روی نسخه‌های baseline موفق alpha.4 pin شده‌اند.
- Bootstrap آزمایشی `13811381`، تغییر اجباری رمز و ابطال دائمی رمز اولیه حفظ شده است.
- دیتای واقعی شرکت در این بسته وجود ندارد؛ Seed فقط 36 رکورد Synthetic/Demo دارد.

Artifact موفق مورد انتظار:

`HRM-0.2.0-alpha.3-Tested-Setup`

Artifact خطا:

`HRM-0.2.0-alpha.3-Failure-Logs`
