@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================================
echo   HRM v0.4.0-alpha.3 - isolated guarded GitHub CI push
echo ============================================================
echo.

where git.exe >nul 2>&1 || (echo ERROR: git.exe not found.& exit /b 1)
where python.exe >nul 2>&1 || (echo ERROR: python.exe not found.& exit /b 1)

git rev-parse --is-inside-work-tree >nul 2>&1 || (echo ERROR: run this from the HRM Git repository root.& exit /b 1)
git show-ref --verify --quiet refs/heads/feat/real-data-import-v040a2
if errorlevel 1 (
  git switch -c feat/real-data-import-v040a2
) else (
  git switch feat/real-data-import-v040a2
)
if errorlevel 1 (
  echo ERROR: could not select the Enterprise data integration feature branch.
  exit /b 1
)

echo Running mandatory v0.4.0-alpha.3 isolated local gates before staging...
call "%~dp0APPLY-V040A3.cmd"
if errorlevel 1 (
  echo ERROR: local v0.4.0-alpha.3 gates failed. Nothing will be committed or pushed.
  exit /b 1
)

set "HRM_GATE_PYTHON=%CD%\.venv\Scripts\python.exe"
if not exist "%HRM_GATE_PYTHON%" (
  echo ERROR: isolated source-gate Python is missing after validation.
  exit /b 1
)

git add -A
if errorlevel 1 exit /b 1

echo Validating clean-checkout tracking contract after staging...
"%HRM_GATE_PYTHON%" ci\validate_package_contract.py --require-git-tracked
if errorlevel 1 (
  echo ERROR: clean-checkout contract failed. Nothing will be committed or pushed.
  exit /b 1
)

git diff --cached --check
if errorlevel 1 (
  echo ERROR: staged diff check failed. Nothing will be committed or pushed.
  exit /b 1
)

git commit -m "fix: install pinned source gates before alpha3 validation"
if errorlevel 1 exit /b 1

git push -u origin feat/real-data-import-v040a2
if errorlevel 1 exit /b 1

echo.
echo PASS: v0.4.0-alpha.3 was pushed. Watch GitHub Actions for Windows validation.
exit /b 0
