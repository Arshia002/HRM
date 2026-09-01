@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================================
echo   HRM v0.5.0-alpha.1 - full native v4.9 UI guarded push
echo ============================================================
echo.

where git.exe >nul 2>&1 || (echo ERROR: git.exe not found.& exit /b 1)
where python.exe >nul 2>&1 || (echo ERROR: python.exe not found.& exit /b 1)

git rev-parse --is-inside-work-tree >nul 2>&1 || (echo ERROR: run this from the HRM Git repository root.& exit /b 1)
git show-ref --verify --quiet refs/heads/feat/full-v49-ui-v050a1
if errorlevel 1 (
  git switch -c feat/full-v49-ui-v050a1
) else (
  git switch feat/full-v49-ui-v050a1
)
if errorlevel 1 (
  echo ERROR: could not select the full native v4.9 UI feature branch.
  exit /b 1
)

echo Running mandatory v0.5.0-alpha.1 isolated local gates before staging...
call "%~dp0APPLY-V050A1.cmd"
if errorlevel 1 (
  echo ERROR: local v0.5.0-alpha.1 gates failed. Nothing will be committed or pushed.
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

git commit -m "feat: integrate full native v4.9 UI for v0.5 alpha1"
if errorlevel 1 exit /b 1

git push -u origin feat/full-v49-ui-v050a1
if errorlevel 1 exit /b 1

echo.
echo PASS: v0.5.0-alpha.1 was pushed. Watch GitHub Actions for Windows validation.
exit /b 0
