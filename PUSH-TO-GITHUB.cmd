@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================================
echo   HRM v0.3.0-alpha.2 - guarded GitHub CI push
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

git commit -m "feat: add HRM v0.3.0-alpha.2 native v4.9 shell"
if errorlevel 1 exit /b 1

git push origin feat/native-v49-shell
if errorlevel 1 exit /b 1

echo.
echo PASS: v0.3.0-alpha.2 was pushed. Watch GitHub Actions for Windows validation.
exit /b 0
