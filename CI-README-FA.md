# راهنمای CI — HRM v0.3.0-alpha.2

این Build اولین Feature Milestone بعد از Baseline سبز `0.2.0-alpha.3` است و روی Native UI/Branding تمرکز دارد.

## روش اعمال

1. روی Branch `feat/native-v49-shell` بمانید.
2. ZIP را در Root Repository استخراج کنید.
3. `APPLY-V030A2.cmd` را اجرا کنید.
4. پس از PASS، `git add -A` بزنید.
5. `python ci\validate_package_contract.py --require-git-tracked` را اجرا کنید.
6. Commit و Push کنید.
7. Artifact سبز: `HRM-0.3.0-alpha.2-Tested-Setup`.
8. Artifact قرمز: `HRM-0.3.0-alpha.2-Failure-Logs`.

## Windows acceptance path

Package contract -> Source tests -> PyInstaller سه EXE -> Frozen Qt smoke -> Frozen Native UI smoke -> Frozen Server smoke -> Inno Setup -> Clean Install -> `HRMCentralService` -> LocalService + SID/ACL -> TLS -> Desktop Shortcut -> Bootstrap `13811381` -> Forced Password Change -> Bootstrap invalidation -> Upgrade -> Data Preservation -> Uninstall.

دیتای واقعی شرکت در این Candidate وجود ندارد.
