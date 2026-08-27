# HRM v0.2.0-alpha.1 — CI Build Package

این بسته **Setup نهایی نیست**. هدف آن Push شدن به Repository و اجرای Build/Test واقعی روی Windows Server 2022 در GitHub Actions است.

## روند تأیید

1. محتویات ZIP را روی سورس Repository قرار دهید.
2. `PUSH-TO-GITHUB.cmd` را اجرا کنید یا دستورات Git پایین را دستی بزنید.
3. Workflow با نام `HRM - Windows Build and Install Test` باید اجرا شود.
4. تا سبز شدن کامل Workflow، هیچ فایل Setup نهایی تلقی نمی‌شود.
5. در حالت سبز Artifact با نام `HRM-0.2.0-alpha.1-Tested-Setup` مبنای تست دستی است.
6. در حالت قرمز Artifact با نام `HRM-0.2.0-alpha.1-Failure-Logs` برای رفع اشکال استفاده می‌شود.

## تست‌هایی که GitHub Windows CI انجام می‌دهد

- Unit tests و Package tests
- PyInstaller برای HRM.exe / HRMServer.exe / HRMService.exe
- ساخت Installer آفلاین با Inno Setup
- Clean Install نوع Full
- Windows Service `HRMCentral`
- اجرای سرویس با `LocalSystem`
- Service SID و ACL روی `C:\ProgramData\HRM-Kermanshah`
- TLS health check روی `https://127.0.0.1:8765`
- وجود Desktop shortcut
- ورود اولیه با Bootstrap secret مورد تأیید پروژه
- الزام تغییر رمز قبل از دسترسی به Dashboard
- تغییر رمز به رمز قوی تستی
- رد شدن Bootstrap secret بعد از تغییر رمز
- حذف `FIRST_LOGIN.txt` بعد از تغییر رمز
- In-place Upgrade با اجرای مجدد همان Installer
- حفظ دیتابیس و فایل Sentinel بعد از Upgrade
- معتبر ماندن رمز جدید بعد از Upgrade
- رد ماندن Bootstrap secret بعد از Upgrade
- Uninstall
- حذف Service در Uninstall
- حفظ دیتابیس عملیاتی بعد از Uninstall

## Push دستی از CMD

```cmd
git switch -C feat/native-v49-shell
git add -A
git commit -m "build: prepare HRM v0.2.0-alpha.1 Windows CI candidate"
git push -u origin feat/native-v49-shell
```

Actions:
`https://github.com/Arshia002/HRM/actions`

## قانون Release

`Local tests PASS` → `GitHub Windows CI GREEN` → `دانلود Artifact سبز` → `تست دستی مدیر پروژه` → `Release`
