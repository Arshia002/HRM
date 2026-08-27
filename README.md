# SazmanHR Enterprise 16.0.7 — Direct Windows Setup Candidate

نسخه جدید، مستقل و بومی سامانه منابع انسانی و چارت سازمانی است. هیچ کد اجرایی، سرویس، runtime، installer یا حساب کاربری از بسته‌های خراب پیشین در این پروژه وجود ندارد. فقط دیتاست ۱۳۵۶ نفر و ۵۳ صفحه چارت پس از استخراج داده‌محور و پاک‌سازی وارد schema جدید شده است. فضای نصب، AppId، Windows Service، تنظیمات کلاینت و دیتابیس این نسل از تمام نسل‌های قبلی جداست.

## آنچه در نسخه ۱۶ آماده است

- کلاینت مدرن PySide6/Qt و کاملاً دسکتاپ؛ بدون مرورگر و WebView
- Setup ویندوز با سه حالت «کامل»، «سرور مرکزی» و «کلاینت مدیر»
- Windows Service مرکزی و میان‌بر Desktop
- Setup نهایی کاملاً آفلاین؛ بدون نیاز به Python، pip، Qt، مرورگر، PowerShell، winget یا اینترنت روی سیستم مقصد
- جلوگیری قطعی از بازشدن دیتابیس قدیمی با شناسه محصول و نسل schema
- توقف نصب در صورت شکست init، Service یا TLS health؛ Setup دیگر خطا را موفق اعلام نمی‌کند
- SQLite مرکزی؛ کلاینت‌ها هرگز فایل دیتابیس را مستقیم باز نمی‌کنند
- TLS پیش‌فرض با گواهی اختصاصی و pinning اثرانگشت در کلاینت
- نام کاربری مالک اولیه `arshia.shahbazi` و رمز تصادفی یک‌بارمصرف
- نقش‌ها و ریزدسترسی‌های allow/deny سمت سرور
- کنترل ویرایش هم‌زمان با `row_version` و change feed برای پنج مدیر
- migration ترتیبی و کنترل checksum دیتابیس
- پشتیبان خودکار، retention، integrity check و بازیابی آفلاین با safety copy
- audit hash chain و لاگ JSON چرخشی
- گردش کار، اعلان، TOTP MFA، کد بازیابی و داشبورد پایش
- داشبورد و اطلاعات پرسنل/چارت قابل ویرایش
- CI ویندوز برای build، نصب silent، کنترل Service، TLS و دیتابیس

## خروجی قابل استقرار

خروجی رسمی این نسخه فایل مستقیم `SazmanHR-Enterprise-Setup-x64.exe` است. ابزارهای build فقط در محیط CI ویندوز اجرا می‌شوند؛ رایانه سرور و مدیران به Python، pip، Qt، PowerShell، winget، مرورگر یا اینترنت نیاز ندارند.

## ساخت مجدد Setup توسط تیم توسعه

پس از Extract، روی فایل زیر دوبار کلیک کنید:

```text
BUILD-SETUP.cmd
```

این لانچر مستقیماً با Python اجرا می‌شود و به PowerShell وابسته نیست. Python 3.11 و Inno Setup را در صورت نیاز از `winget` نصب می‌کند، آزمون‌ها را اجرا می‌کند و Setup را می‌سازد. خروجی:

```text
build-output\installer\SazmanHR-Enterprise-Setup-x64.exe
```

در پایان همان Setup باز می‌شود. اگر build متوقف شود، پنجره باز می‌ماند و علت در `build-setup-bootstrap.log` و `build-output\build.log` ذخیره می‌شود. سورس را باید کامل روی Desktop یا مسیر قابل‌نوشتن مانند `C:\SazmanHR-Enterprise-16.0.7` Extract کرد؛ اجرای مستقیم از داخل ZIP یا `Program Files` پشتیبانی نمی‌شود.

Python و Inno Setup فقط ابزار «کارخانه ساخت» روی رایانه سازنده هستند. فایل EXE نهایی همه runtimeهای لازم را داخل خود دارد و روی سرور یا رایانه مدیران چیزی نصب یا دانلود نمی‌کند. برای استقرار اداره فقط Setup نهایی و SHA-256 تحویل IT می‌شود، نه پوشه build.

## ورود اولیه

پس از نصب کامل یا سرور، اطلاعات زیر روی ماشین مرکزی ساخته می‌شود:

```text
C:\ProgramData\SazmanHR-Enterprise\FIRST_LOGIN.txt
```

- Username: `arshia.shahbazi`
- Password: تصادفی و یک‌بارمصرف
- TLS SHA-256: اثرانگشت گواهی سرور

در اولین ورود، کلاینت اثرانگشت TLS را برای تأیید نمایش می‌دهد و تغییر رمز اجباری است. پس از تغییر رمز مالک، فایل اطلاعات اولیه حذف می‌شود.

## ساختار بسته

| مسیر | محتوا |
|---|---|
| `src/sazmanhr` | سرویس، Qt Client، امنیت، TLS، migration و عملیات |
| `data/seed` | دیتابیس اولیه پاک‌سازی‌شده بدون حساب و نشست |
| `data/export` | خروجی فشرده دیتاست پرسنل و چارت |
| `build/windows` | PyInstaller، Windows Service، Inno Setup و smoke test |
| `.github/workflows` | CI ویندوز و artifact نصب‌کننده |
| `tests` | آزمون دیتابیس، API، TLS، MFA و پنج کلاینت |
| `docs` | استقرار، ساخت، امنیت، بازیابی و پذیرش Windows |

## جداسازی از نسخه‌های قدیمی

- مسیر برنامه: `C:\Program Files\SazmanHR Enterprise`
- مسیر داده جدید: `C:\ProgramData\SazmanHR-Enterprise`
- دیتابیس جدید: `hrm.sqlite`
- سرویس جدید: `SazmanHREnterpriseCentral`
- مسیر قدیمی `C:\ProgramData\SazmanHR` نه خوانده، نه ویرایش و نه حذف می‌شود.

## اصل شبکه

فایل SQLite نباید در Network Share قرار گیرد. فقط سرویس مرکزی آن را باز می‌کند و مدیران از طریق API رمزنگاری‌شده متصل می‌شوند. مهاجرت به PostgreSQL یا SQL Server زمانی انجام می‌شود که سنجه‌های واقعی مقیاس، تعداد کاربران یا حجم workflow آن را لازم کنند.
