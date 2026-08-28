@echo off
setlocal
cd /d "%~dp0"
echo [HRM] v0.4.0-alpha.1 local source gates
where git >nul 2>nul || (echo FAIL: git not found.& exit /b 1)
where python >nul 2>nul || (echo FAIL: python not found.& exit /b 1)
git rev-parse --is-inside-work-tree >nul 2>nul || (echo FAIL: run this from the HRM Git repository root.& exit /b 1)
if not exist "ci\validate_package_contract.py" (
  echo FAIL: v0.3.x baseline contract validator was not found.
  echo This package must be overlaid on the existing green HRM repository, not used standalone for production build.
  exit /b 1
)
python ci\apply_v040a1.py || exit /b 1
python ci\validate_v040a1_migration.py || exit /b 1
python ci\validate_package_contract.py || exit /b 1
echo PASS: HRM v0.4.0-alpha.1 local source gates passed.
exit /b 0
