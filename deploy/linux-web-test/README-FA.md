# HRM 0.8.0-rc.1 — Linux Web Test

این پکیج فقط برای تست Linux/Browser است و **Production نیست**. هسته API، دیتابیس، Audit، RBAC، Migration و Personnel Movement با نسخه Windows مشترک است.

## اجرا

پیش‌نیاز: Docker + Docker Compose v2.

```bash
cd deploy/linux-web-test
./start.sh
```

سپس در همان سیستم باز کنید:

```text
http://127.0.0.1:8080/
```

`start.sh` در اولین اجرا یک رمز تصادفی قوی در `.env` می‌سازد. فایل `.env` را Commit یا منتشر نکنید. در ورود اول تغییر رمز اجباری است.

## توقف

```bash
./stop.sh
```

## پاک‌کردن کامل داده آزمایشی

```bash
docker compose down -v
```

## نکته امنیتی

Compose به‌طور پیش‌فرض فقط روی `127.0.0.1` Bind می‌شود. برای تست LAN باید Binding را آگاهانه تغییر دهید. حالت `--tls-mode off` فقط برای این Test Build است؛ نسخه Windows سازمانی همچنان TLS/Pinning دارد.
