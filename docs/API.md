# LAN API

همه پاسخ‌ها JSON با UTF-8 هستند. ارتباط عملیاتی HTTPS است و کلاینت اثرانگشت گواهی را کنترل می‌کند. به‌جز health و login، هدر `Authorization: Bearer TOKEN` الزامی است.

| روش | مسیر | کاربرد |
|---|---|---|
| GET | `/api/health` | سلامت سرویس |
| POST | `/api/login` | ورود |
| POST | `/api/change-password` | تغییر رمز |
| GET/POST | `/api/personnel` | جستجو و ذخیره پرسنل |
| GET/PUT | `/api/chart/pages/{page}` | مشاهده و ذخیره صفحه چارت |
| GET | `/api/dashboard` | آمار و ویجت‌ها |
| POST/DELETE | `/api/dashboard/widgets` | مدیریت ویجت |
| GET | `/api/changes?since=N` | همگام‌سازی تغییرات |
| GET | `/api/audit` | گزارش ممیزی |
| GET/POST | `/api/users` | کاربران |
| PUT | `/api/users/{id}/permissions` | ریزدسترسی allow/deny |
| POST | `/api/backup` | پشتیبان مرکزی |
| GET | `/api/backups` | فهرست پشتیبان‌ها |
| GET/POST | `/api/workflows` | گردش کار |
| POST | `/api/workflows/{id}/transition` | تغییر وضعیت گردش کار |
| GET | `/api/notifications` | اعلان‌ها |
| POST | `/api/mfa/setup` | آغاز تنظیم TOTP |
| POST | `/api/mfa/confirm` | تأیید TOTP و دریافت کدهای بازیابی |
| GET | `/api/monitoring` | سنجه‌ها و رخدادهای عملیاتی |

خطای تعارض نسخه با HTTP 409 و کد `version_conflict` برمی‌گردد. کلاینت باید داده تازه را دریافت و تغییر را دوباره اعمال کند.

اگر MFA فعال باشد، login بدون OTP با HTTP 401 و کد `mfa_required` پاسخ می‌دهد. بازیابی دیتابیس عمداً API آنلاین ندارد و فقط با CLI آفلاین سرور انجام می‌شود.
