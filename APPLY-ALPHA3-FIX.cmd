@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================================
echo   HRM v0.2.0-alpha.3 - apply and validate CI fix
echo ============================================================
echo.

where git.exe >nul 2>&1
if errorlevel 1 (
  echo ERROR: git.exe was not found.
  exit /b 1
)
where python.exe >nul 2>&1
if errorlevel 1 (
  echo ERROR: python.exe was not found.
  exit /b 1
)

rem Remove files left by failed/obsolete alpha overlays. Historical root-cause
rem documents are kept intentionally. Ignore missing files safely.
git rm -f --ignore-unmatch "build/windows/SazmanHR.iss" "assets/SazmanHR.ico" "assets/SazmanHR.png" >nul 2>&1
git rm -f --ignore-unmatch "HRM-ALPHA1-NOTES.md" "TEST-REPORT-HRM-v0.2.0-alpha.1.md" >nul 2>&1
git rm -f --ignore-unmatch "HRM-ALPHA2-NOTES.md" "TEST-REPORT-HRM-v0.2.0-alpha.2.md" "APPLY-ALPHA2-FIX.cmd" >nul 2>&1

rem Local caches are never part of the public CI overlay. Cleaning them here
rem makes the operator's worktree match the package contract as closely as possible.
if exist ".pytest_cache" rmdir /s /q ".pytest_cache"
for /d /r %%D in (__pycache__) do @if exist "%%D" rmdir /s /q "%%D" 2>nul

echo [1/3] Packaging contract...
python ci\validate_package_contract.py
if errorlevel 1 goto :fail

echo.
echo [2/3] Python compile check...
python -m compileall -q src tests tools ci build\windows
if errorlevel 1 goto :fail

echo.
echo [3/3] Source unit/integration tests...
set "PYTHONPATH=%CD%\src"
python -m unittest discover -s tests -v
if errorlevel 1 goto :fail

echo.
echo PASS: alpha.3 local source gates passed.
echo Next: git add -A, then run:
echo   python ci\validate_package_contract.py --require-git-tracked
echo before commit/push.
echo.
git status
exit /b 0

:fail
echo.
echo ERROR: alpha.3 validation failed. Do NOT commit or push.
exit /b 1
