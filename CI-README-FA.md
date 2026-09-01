# راهنمای CI — HRM v0.5.0-alpha.1

این Build رابط Native کامل v4.9 را روی Baseline سبز `0.4.0-alpha.3` ادغام می‌کند.

## روش اعمال

1. ZIP را در Root همان Repository استخراج کنید.
2. فقط `PUSH-TO-GITHUB.cmd` را اجرا کنید.
3. اسکریپت Branch `feat/full-v49-ui-v050a1` را می‌سازد یا انتخاب می‌کند.
4. `APPLY-V050A1.cmd`، Regression کامل و clean-index gate اجباری اجرا می‌شوند.
5. Artifact سبز: `HRM-0.5.0-alpha.1-Tested-Setup`.
6. Artifact قرمز: `HRM-0.5.0-alpha.1-Failure-Logs`.

## Windows acceptance path

Package contract -> Source tests -> PyInstaller چهار EXE -> Frozen Qt smoke -> Frozen Native UI smoke -> Frozen Migration smoke -> Frozen Server smoke -> Inno Setup -> Clean Install -> `HRMCentralService` -> LocalService + SID/ACL -> TLS -> Desktop Shortcut -> Random Bootstrap -> Forced Password Change -> Bootstrap invalidation -> Upgrade -> Data Preservation -> Uninstall.

دیتای واقعی شرکت در این Candidate وجود ندارد.
