# راهنمای استقرار در اداره

## پیش‌نیاز

- پروفایل Production: Windows Server 2022 نسخه ۶۴ بیتی، ترجیحاً VM/Server اختصاصی
- IP ثابت یا نام DNS داخلی برای سرور
- باز بودن TCP پورت 8765 فقط در پروفایل Domain/Private
- حساب دارای دسترسی Administrator برای نصب سرویس

## نصب سرور مرکزی

1. فایل Setup را با Run as administrator اجرا کنید.
2. حالت «سرور مرکزی و کلاینت مدیریت» را انتخاب کنید.
3. آدرس محلی پیش‌فرض `https://127.0.0.1:8765` را نگه دارید.
4. پس از پایان، سرویس `HRMCentralService` باید در Services وضعیت Running داشته باشد.
5. اطلاعات ورود یک‌بارمصرف را از `C:\ProgramData\HRM-Kermanshah\FIRST_LOGIN.txt` بردارید.
6. با نام کاربری `arshia.shahbazi` وارد شوید و بلافاصله رمز را تغییر دهید؛ فایل اطلاعات اولیه خودکار حذف می‌شود.

دیتابیس عملیاتی در `C:\ProgramData\HRM-Kermanshah\hrm.sqlite` قرار می‌گیرد. حذف برنامه عمداً این داده را پاک نمی‌کند تا سوابق سازمان از دست نرود. مسیر قدیمی `C:\ProgramData\SazmanHR` متعلق به نسل‌های پیشین است و این نسخه هرگز آن را باز، مهاجرت، ویرایش یا حذف نمی‌کند.

## نصب روی رایانه مدیران

1. Setup را اجرا و «فقط کلاینت مدیریت» را انتخاب کنید.
2. ترجیحاً نام DNS داخلی سرور را به شکل `https://hrm-server:8765` وارد کنید؛ IP داخلی ثابت فقط گزینه جایگزین است.
3. میان‌بر HRM روی Desktop ساخته می‌شود.
4. مدیر با حساب خودش وارد می‌شود؛ برای هر شخص حساب جداگانه بسازید.

## ایجاد کاربران منابع انسانی

پروفایل فعلی سازمان ۶ کاربر است: ۲ Super Admin و ۴ HR Admin. نام فنی نقش‌ها در سامانه به‌ترتیب `owner` و `admin` است.

| نقش | تعداد پیشنهادی | دسترسی |
|---|---:|---|
| `owner` (Super Admin) | 2 | همه کارهای HR + مدیریت کاربران/Permission، Restore، Hard Delete، تنظیمات حساس و ابطال آخرین جابه‌جایی |
| `admin` (HR Admin) | 4 | مشاهده کل شرکت، اطلاعات حساس، ویرایش روزمره، ثبت جابه‌جایی، گزارش و Backup؛ بدون Restore/Hard Delete/مدیریت کاربران |

برای هر شخص حساب جداگانه بسازید. رمز موقت باید حداقل ۱۲ نویسه و شامل دست‌کم سه گروه از حروف کوچک، بزرگ، عدد و نماد باشد و تغییر آن در اولین ورود اجباری است.

تغییر واحد، پست، محل خدمت یا وضعیت سازمانی از «ویرایش» عادی انجام نمی‌شود؛ از «ثبت جابه‌جایی» استفاده کنید تا سابقه قبلی، حکم، تاریخ اجرا و Audit حفظ شود.

## پشتیبان‌گیری

سرویس مرکزی به‌صورت پیش‌فرض هر ۲۴ ساعت یک Backup سالم در `C:\ProgramData\HRM-Kermanshah\backups` می‌سازد و ۳۰ نسخه محلی را نگه می‌دارد.

برای Production باید IT یک مقصد دوم (NAS / File Server / Backup Storage) تعیین کند. در `C:\ProgramData\HRM-Kermanshah\server.json` مقدارهای زیر قابل تنظیم‌اند:

```json
{
  "backup_interval_hours": 24,
  "backup_retention": 30,
  "backup_secondary_dir": "\\BACKUP-SERVER\HRM",
  "backup_secondary_retention": 30
}
```

سرویس نسخه محلی را ابتدا با SQLite integrity check می‌سازد، سپس نسخه ثانویه را کپی و با SHA-256 تطبیق می‌دهد. مسیر واقعی مقصد ثانویه در بسته Diagnostics عمومی افشا نمی‌شود. پیش از تأیید Production حداقل یک Restore آزمایشی از مقصد دوم انجام شود.

## عیب‌یابی سریع

```powershell
Get-Service HRMCentralService
Test-NetConnection SERVER-IP -Port 8765
curl.exe -k https://SERVER-IP:8765/api/health
```

اگر health پاسخ می‌دهد ولی ورود ممکن نیست، زمان رایانه‌ها، نام کاربری، قفل ۱۵ دقیقه‌ای و فعال بودن حساب بررسی شود. اگر سرویس بالا نمی‌آید، Windows Event Viewer و فایل `C:\ProgramData\HRM-Kermanshah\logs\setup-server.log` بررسی شود.

## TLS

TLS در نصب جدید فعال است و برای تست گواهی self-signed اختصاصی تولید می‌شود. در استقرار اداره، `server.json` را روی حالت `custom` قرار دهید و مسیر گواهی و کلید صادرشده توسط CA داخلی را تنظیم کنید. کلاینت‌ها تغییر اثرانگشت گواهی را به‌عنوان رخداد امنیتی رد می‌کنند.

## بازیابی پشتیبان

بازیابی فقط در حالت توقف سرویس انجام شود:

```powershell
Stop-Service HRMCentralService
& 'C:\Program Files\HRM\Server\HRMServer.exe' --data-dir 'C:\ProgramData\HRM-Kermanshah' --restore 'C:\ProgramData\HRM-Kermanshah\backups\BACKUP.sqlite' --init-only
Start-Service HRMCentralService
```

پیش از جایگزینی، سلامت فایل کنترل و از دیتابیس جاری safety copy ساخته می‌شود.
