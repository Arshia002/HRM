@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================================
echo   HRM v0.6.0-beta.1 - protected real-data guarded push
echo ============================================================
echo.

where git.exe >nul 2>&1 || (echo ERROR: git.exe not found.& exit /b 1)
where python.exe >nul 2>&1 || (echo ERROR: python.exe not found.& exit /b 1)

git rev-parse --is-inside-work-tree >nul 2>&1 || (echo ERROR: run this from the HRM Git repository root.& exit /b 1)
git diff --cached --quiet
if errorlevel 1 (
  echo ERROR: Git index already contains staged changes. Unstage them before guarded push.
  exit /b 1
)
if not exist "ci\real-data\hrm-real-data-v060b1.enc" (
  echo ERROR: encrypted real-data bundle is missing. Run PREPARE-REAL-DATA-V060B1.cmd first.
  exit /b 1
)
if not exist "ci\real-data\hrm-real-data-v060b1.enc.sha256" (
  echo ERROR: encrypted real-data checksum is missing.
  exit /b 1
)
if not exist "private-data\hrm-v060b1-fernet.key" (
  echo ERROR: local private key is missing. Nothing will be pushed.
  exit /b 1
)

git check-ignore -q private-data\hrm-v060b1-fernet.key
if errorlevel 1 (
  echo ERROR: private key is not protected by .gitignore. Nothing will be pushed.
  exit /b 1
)

git show-ref --verify --quiet refs/heads/feat/organizational-pilot-v060b1
if errorlevel 1 (
  git switch -c feat/organizational-pilot-v060b1
) else (
  git switch feat/organizational-pilot-v060b1
)
if errorlevel 1 (
  echo ERROR: could not select the organizational pilot feature branch.
  exit /b 1
)
git merge-base --is-ancestor 8e3eb3baecb46d2a0f964322584e668a6e926ce2 HEAD
if errorlevel 1 (
  echo ERROR: current branch is not based on tested tag v0.5.0-alpha.1.
  exit /b 1
)

echo Running mandatory v0.6.0-beta.1 isolated local gates before staging...
call "%~dp0APPLY-V060B1.cmd"
if errorlevel 1 (
  echo ERROR: local v0.6.0-beta.1 gates failed. Nothing will be committed or pushed.
  exit /b 1
)

set "HRM_GATE_PYTHON=%CD%\.venv\Scripts\python.exe"
if not exist "%HRM_GATE_PYTHON%" (
  echo ERROR: isolated source-gate Python is missing after validation.
  exit /b 1
)

"%HRM_GATE_PYTHON%" ci\stage_v060b1_overlay.py
if errorlevel 1 (
  echo ERROR: protected overlay staging failed. Nothing will be committed or pushed.
  exit /b 1
)

git diff --cached --name-only | findstr /i /r /c:"\.key$" /c:"^private-data/" >nul
if not errorlevel 1 (
  echo ERROR: a private key or private-data path was staged. Nothing will be committed or pushed.
  exit /b 1
)

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

git commit -m "feat: add protected real-data CI and pilot gates for v0.6 beta1"
if errorlevel 1 exit /b 1

git push -u origin feat/organizational-pilot-v060b1
if errorlevel 1 exit /b 1

echo.
echo PASS: v0.6.0-beta.1 was pushed. Watch the real-data-validation Environment job.
echo If Environment reviewers are configured, approve the pending deployment in GitHub.
exit /b 0
