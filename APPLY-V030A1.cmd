@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================================
echo   HRM v0.3.0-alpha.1 - native v4.9 shell candidate
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

rem Remove obsolete overlay helper files so the worktree matches this candidate.
git rm -f --ignore-unmatch "APPLY-ALPHA3-FIX.cmd" "HRM-ALPHA3-NOTES.md" "TEST-REPORT-HRM-v0.2.0-alpha.3.md" >nul 2>&1

if exist ".pytest_cache" rmdir /s /q ".pytest_cache"
for /d /r %%D in (__pycache__) do @if exist "%%D" rmdir /s /q "%%D" 2>nul

echo [1/4] Packaging + branding contract...
python ci\validate_package_contract.py
if errorlevel 1 goto :fail

echo.
echo [2/4] Python compile check...
python -m compileall -q src tests tools ci build\windows
if errorlevel 1 goto :fail

echo.
echo [3/4] Source unit/integration/UI contract tests...
set "PYTHONPATH=%CD%\src"
python -m unittest discover -s tests -v
if errorlevel 1 goto :fail

echo.
echo [4/4] Git whitespace check...
git --no-pager diff --check 2>nul
if errorlevel 1 goto :fail

echo.
echo PASS: HRM v0.3.0-alpha.1 local source gates passed.
echo Next:
echo   git add -A
echo   python ci\validate_package_contract.py --require-git-tracked
echo   git commit -m "feat: add HRM v0.3.0-alpha.1 native v4.9 shell"
echo   git push origin feat/native-v49-shell
echo.
git status
exit /b 0

:fail
echo.
echo ERROR: v0.3.0-alpha.1 validation failed. Do NOT commit or push.
exit /b 1
