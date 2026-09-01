@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo [HRM] v0.4.0-alpha.2 local source gates
where git.exe >nul 2>&1 || (echo FAIL: git not found.& exit /b 1)
where python.exe >nul 2>&1 || (echo FAIL: python not found.& exit /b 1)
git rev-parse --is-inside-work-tree >nul 2>&1 || (echo FAIL: run from the HRM Git repository root.& exit /b 1)
python ci\validate_v040a2_migration.py || exit /b 1
python ci\validate_package_contract.py || exit /b 1
echo PASS: HRM v0.4.0-alpha.2 local source gates passed.
exit /b 0
