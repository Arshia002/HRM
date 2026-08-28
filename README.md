# HRM v0.3.0-alpha.1 — Native v4.9 Shell CI Candidate

این Candidate روی Baseline سبز `0.2.0-alpha.3` ساخته شده است. هدف این Milestone تغییر زیرساخت Windows نیست؛ تمرکز روی UI Native، Login، Dashboard shell و Branding نهایی HRM است.

## تغییرات اصلی

- Login جدید Native Qt و RTL با Branding شرکت توزیع نیروی برق استان کرمانشاه.
- Sidebar سمت راست + Header + Connection badge + User panel.
- Dashboard کارت‌محور با ظاهر یکپارچه و مناسب رزولوشن‌های سازمانی.
- لوگوی سازمانی روی Application و Installer.
- اجرای `HRM.exe --ui-smoke-test` در Windows Builder قبل از Inno Setup.
- حفظ Bootstrap `13811381`، تغییر اجباری رمز و ابطال رمز اولیه.
- حفظ کامل Service/TLS/ACL/Upgrade/Uninstall از Baseline سبز.
- عدم وجود دیتای واقعی در Git؛ Seed فقط 36 رکورد Demo/Synthetic است.

## اعمال روی Branch

ZIP را در Root همان Repository استخراج کنید و اجرا کنید:

```cmd
APPLY-V030A1.cmd
```

پس از PASS:

```cmd
git add -A
python ci\validate_package_contract.py --require-git-tracked
git commit -m "feat: add HRM v0.3.0-alpha.1 native v4.9 shell"
git push origin feat/native-v49-shell
```

## Artifactها

- موفق: `HRM-0.3.0-alpha.1-Tested-Setup`
- ناموفق: `HRM-0.3.0-alpha.1-Failure-Logs`

این Candidate زمانی Windows-Tested است که Build + Frozen UI Smoke + Inno Setup + Clean Install + Login + Password Change + Service/TLS/ACL + Upgrade + Data Preservation + Uninstall در GitHub Actions سبز شوند.
