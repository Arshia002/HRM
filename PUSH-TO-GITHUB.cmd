@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================================
echo   HRM v0.2.0-alpha.3 - guarded GitHub CI push
echo ============================================================
echo.

where git.exe >nul 2>&1 || (echo ERROR: git.exe not found.& exit /b 1)
where python.exe >nul 2>&1 || (echo ERROR: python.exe not found.& exit /b 1)

git add -A
if errorlevel 1 exit /b 1

echo Validating clean-checkout tracking contract after staging...
python ci\validate_package_contract.py --require-git-tracked
if errorlevel 1 (
  echo ERROR: clean-checkout contract failed. Nothing will be committed or pushed.
  exit /b 1
)

git diff --cached --check
if errorlevel 1 (
  echo ERROR: staged diff check failed. Nothing will be committed or pushed.
  exit /b 1
)

git commit -m "fix: make HRM alpha.3 CI package reproducible and restore proven Windows upgrade path"
if errorlevel 1 exit /b 1

git push origin feat/native-v49-shell
if errorlevel 1 exit /b 1

echo.
echo PASS: alpha.3 was pushed. Watch GitHub Actions for Windows validation.
exit /b 0
