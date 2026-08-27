# گزارش آزمون SazmanHR Enterprise 16.0.7

تاریخ: ۲۰۲۶-۰۸-۲۴

| حوزه | نتیجه محیط فعلی |
|---|---|
| compile و AST همه ماژول‌های Python و Qt | موفق |
| سلامت seed و شمارش ۱۳۵۶ پرسنل/۵۳ صفحه | موفق |
| نبود حساب، نشست و باینری قدیمی در seed | موفق |
| PBKDF2، TOTP و کد بازیابی | موفق |
| قفل حساب و ماندگاری شمارنده ورود ناموفق | موفق |
| TLS واقعی و pinning اثرانگشت | موفق |
| migration نسخه‌های ۲ تا ۵ و checksum | موفق |
| RBAC و deny اختصاصی کاربر | موفق |
| API، ویرایش، تعارض و change feed | موفق |
| پنج مدیر هم‌زمان از طریق شبکه API | موفق |
| گردش کار و اعلان | موفق |
| backup، integrity و restore safety copy | موفق |
| audit hash chain و monitoring | موفق |
| نبود مرورگر/WebView/Tk در کلاینت نهایی | موفق |
| اعتبار نحوی سازنده بومی Windows با Python | موفق |
| نبود فراخوانی PowerShell در لانچر یک‌کلیکی | موفق |
| بسته‌شدن handle اتصال SQLite پس از context | موفق |
| جداسازی و عدم دست‌کاری دیتابیس قدیمی | موفق |
| هویت product/schema روی seed و restore | موفق |
| fail-fast بودن provisioning در Inno Setup | موفق |
| بسته‌شدن handler لاگ و حذف واقعی `server.jsonl` در Windows | موفق |
| چاپ امن مسیرهای فارسی در کنسول‌های Windows با charmap محدود | موفق |
| نبود MsgBox غیرقابل‌خاموش‌شدن در نصب silent | موفق |
| timeout و لاگ جزئی برای فرایندهای آزمون نصب Windows | موفق |
| ترتیب ثبت سرویس، Service SID، ACL، سخت‌سازی و health نهایی | موفق |
| کنترل LocalSystem، ACE مؤثر Modify و لاگ تشخیصی ACL در Windows | موفق |
| پاسخ سبک TLS/service/database-ready پس از ACL | موفق |
| نبود دسترسی مستقیم Runner به فایل‌های محافظت‌شده پس از ACL | موفق |
| ثبت مرحله‌ای Inno و جمع‌آوری لاگ مستقل از ACL | موفق |

مجموع فعلی: ۳۴ آزمون خودکار، بدون خطا.

موارد زیر فقط در Windows قابل تأیید هستند و Workflow مربوط به آن‌ها در `.github/workflows/windows-build.yml` قرار دارد:

- build باینری Qt و Windows Service
- compile شدن Inno Setup
- نصب silent روی Windows Server 2022 runner
- Running شدن سرویس مرکزی
- پاسخ TLS health و database-ready از داخل سرویس پس از نصب
- وجود دیتابیس و اطلاعات ورود اولیه

نسخه ۱۶.۰.۷ مسیر health اثبات‌شده را حفظ می‌کند، حساب Runner را از فایل‌های محافظت‌شده دور نگه می‌دارد و هر مرحله نصب را در لاگ رسمی Setup ثبت می‌کند. تولید EXE و نصب سرویس در CI واقعی Windows انجام و فقط artifact تأییدشده منتشر می‌شود.
