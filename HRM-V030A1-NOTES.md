# HRM v0.3.0-alpha.1 — Native v4.9 Shell Candidate

این نسخه روی Baseline سبز `HRM 0.2.0-alpha.3` ساخته شده و زیرساخت اثبات‌شده Windows را عمداً حفظ می‌کند.

## هدف این Build

- بازطراحی Login به‌صورت Native Qt و RTL.
- پوسته مدیریتی نزدیک به ساختار نسخه 4.9: Sidebar سمت راست، Header، Dashboard و وضعیت اتصال.
- Branding کامل HRM و شرکت توزیع نیروی برق استان کرمانشاه.
- استفاده از لوگوی سازمانی در برنامه و Installer.
- حفظ Bootstrap اولیه `13811381` و Change Password اجباری.
- عدم ورود داده واقعی پرسنلی؛ Seed این Candidate فقط Synthetic/Demo است.

## مواردی که نباید Regression کنند

- Windows Service: `HRMCentralService`
- Service account: `NT AUTHORITY\LocalService`
- TLS / ACL / Firewall
- Upgrade از Baseline سبز قبلی و حفظ داده
- Uninstall با حفظ Data Directory
- Server / Client / Full installer modes

## Gate جدید UI

Builder علاوه بر Qt runtime smoke test، فایل Frozen `HRM.exe` را با `--ui-smoke-test` اجرا می‌کند و Login + Dashboard shell را بدون Network می‌سازد. این Gate قبل از Inno Setup اجرا می‌شود تا Asset یا Qt Widget regression پیش از ساخت Setup متوقف شود.
