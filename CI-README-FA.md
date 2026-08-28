# راهنمای CI — HRM v0.2.0-alpha.2

این بسته Patch کامل Candidate ناموفق alpha.1 است.

1. روی Branch `feat/native-v49-shell` بمانید.
2. ZIP را در Root همان Repository استخراج کنید.
3. `APPLY-ALPHA2-FIX.cmd` را اجرا کنید.
4. فقط اگر `ALL PACKAGE CONTRACT CHECKS PASSED` دیدید، Commit کنید.
5. Push کنید تا Workflow `HRM - Windows Build and Install Test` اجرا شود.
6. اگر سبز شد Artifact `HRM-0.2.0-alpha.2-Tested-Setup` را دانلود کنید.
7. اگر قرمز شد Artifact `HRM-0.2.0-alpha.2-Failure-Logs` را برای بررسی بعدی نگه دارید.

دستورها:

```cmd
git add -A
git commit -m "fix: repair HRM alpha.2 Windows packaging contract"
git push origin feat/native-v49-shell
```

تست Windows شامل Build سه EXE، ساخت Inno Setup، نصب کامل، HRMCentral، TLS، ACL، Desktop Shortcut، ورود `13811381`، تغییر اجباری رمز، ابطال رمز Bootstrap، Upgrade، حفظ داده و Uninstall است.

### اصلاح ci.2
اگر Repository فایل‌های مستندات با نام فارسی دارد، حذفشان نکنید. این فایل‌ها جزو payload نصب نیستند. Gate جدید فقط فایل‌های تعریف‌شده در `PACKAGE-MANIFEST.json` و Sourceهای `HRM.iss` را از نظر مسیر ASCII کنترل می‌کند.
