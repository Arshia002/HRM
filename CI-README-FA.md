# راهنمای CI — HRM v0.6.0-beta.1

این Build رابط Native کامل v4.9 را روی Baseline تگ‌شده `v0.5.0-alpha.1` حفظ و مسیر تست کنترل‌شده دیتای واقعی را اضافه می‌کند.

## روش اعمال

1. ZIP را در Root همان Repository استخراج کنید.
2. چهار فایل تأییدشده را فقط در پوشه‌ای خارج از Repository قرار دهید.
3. `PREPARE-REAL-DATA-V060B1.cmd` را با مسیر آن پوشه اجرا کنید.
4. با `CONFIGURE-REAL-DATA-SECRET-V060B1.cmd` کلید را در Environment Secret تنظیم کنید.
5. `PUSH-TO-GITHUB.cmd` را اجرا کنید؛ Branch هدف `feat/organizational-pilot-v060b1` است.
6. Artifact سبز: `HRM-0.6.0-beta.1-Tested-Setup`.
7. Artifact قرمز: `HRM-0.6.0-beta.1-Failure-Logs`.

## Windows acceptance path

Package contract -> Source tests -> Protected real-data full cycle -> PyInstaller چهار EXE -> Frozen Qt/UI/Migration/Server smoke -> Inno Setup -> Clean Install -> `HRMCentralService` -> LocalService + SID/ACL -> TLS -> Desktop Shortcut -> Random Bootstrap -> Forced Password Change -> Bootstrap invalidation -> Upgrade -> Data Preservation -> Uninstall.

Artifactها فقط شواهد تجمیعی دارند. فایل خام، دیتابیس موقت، کلید و خود بسته رمز‌شده Upload نمی‌شوند.
