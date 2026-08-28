# HRM v0.4.0-alpha.1 — Real Data Import & Migration

## Purpose
Add a guarded, auditable import pipeline without modifying the production HRM database directly and without committing real company data to Git.

## Safety boundary
1. Input workbooks live only in a private local folder.
2. Dry Run reads, normalizes, reconciles and writes only summary/issue reports.
3. Staging is refused whenever reconciliation has any `error`.
4. Production database/API integration is intentionally **not** guessed in this patch because the v0.3.0-alpha.2 source tree/database contract must be reviewed first.
5. The package does not modify the HRMCentralService, TLS, ACL, installer, bootstrap login, UI shell or existing database migrations.

## Expected private source files
The project history names these data sources:
- `اکسل رسمی.xls`
- `اکسل شرکتی - حجمی - پیمانکاری.xls`
- `اکسل پست با نام.xlsx`
- `شهرستان.xls`

Do not add them to Git.

## Dry Run
```bat
python -m tools.real_data_migration --input-dir "D:\HRM-Private-Data" --output-dir "D:\HRM-Migration-Output"
```

For the approved-chart count reconciliation previously identified in the project history:
```bat
python -m tools.real_data_migration --input-dir "D:\HRM-Private-Data" --output-dir "D:\HRM-Migration-Output" --expected-fixed 535 --expected-named 32
```

## Private staging
Only after the Dry Run shows zero errors:
```bat
python -m tools.real_data_migration --input-dir "D:\HRM-Private-Data" --output-dir "D:\HRM-Migration-Output" --expected-fixed 535 --expected-named 32 --stage
```

This creates `staging.sqlite`; it does not touch the production HRM database.

## Legacy XLS
`.xlsx` is supported through the baseline's existing `openpyxl` if available. `.xls` requires `xlrd`. This patch deliberately does not change/pin dependencies because the exact v0.3.0-alpha.2 dependency lock is not available in the current build context. Review the baseline lock before adding `xlrd`, or privately convert legacy `.xls` files to `.xlsx` outside Git.

## Git workflow
Recommended branch: `feat/real-data-import-v040a1`.

Run:
```bat
APPLY-V040A1.cmd

git add -A
python ci\validate_v040a1_migration.py
python ci\validate_package_contract.py --require-git-tracked

git commit -m "feat: add HRM v0.4.0-alpha.1 guarded real-data migration"
git push origin feat/real-data-import-v040a1
```

The existing baseline regression/build workflow must remain mandatory on GitHub Actions.
