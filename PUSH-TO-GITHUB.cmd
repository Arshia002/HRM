@echo off
setlocal EnableExtensions
cd /d "%~dp0"

where git.exe >nul 2>&1 || (echo ERROR: git.exe not found.& exit /b 1)
where python.exe >nul 2>&1 || (echo ERROR: python.exe not found.& exit /b 1)

for /f "delims=" %%V in ('python ci\release_identity.py --print version') do set "HRM_VERSION=%%V"
for /f "delims=" %%R in ('python ci\release_identity.py --print package_revision') do set "HRM_PACKAGE_REVISION=%%R"
for /f "delims=" %%B in ('python ci\release_identity.py --print branch') do set "HRM_PILOT_BRANCH=%%B"
for /f "delims=" %%C in ('python ci\release_identity.py --print baseline_commit') do set "HRM_BASELINE_COMMIT=%%C"

echo ============================================================
echo   HRM %HRM_VERSION% - guarded final production release-candidate push
echo   Package: %HRM_PACKAGE_REVISION%
echo ============================================================
echo.

git rev-parse --is-inside-work-tree >nul 2>&1 || (echo ERROR: run this from the HRM Git repository root.& exit /b 1)
git diff --cached --quiet
if errorlevel 1 (
  echo ERROR: Git index already contains staged changes. Unstage them before guarded push.
  exit /b 1
)
if not exist "ci\real-data\hrm-real-data-v060b1.enc" (
  echo ERROR: the tested encrypted v060b1 real-data bundle is missing.
  echo Restore it from the tested beta branch/tag; do NOT create a new plaintext artifact.
  exit /b 1
)
if not exist "ci\real-data\hrm-real-data-v060b1.enc.sha256" (
  echo ERROR: encrypted real-data checksum is missing.
  exit /b 1
)
if not exist "private-data\hrm-v060b1-fernet.key" (
  echo ERROR: the existing beta Fernet key is missing from private-data.
  echo Copy the SAME protected key from the clean beta workspace. Do not regenerate it.
  exit /b 1
)

git check-ignore -q private-data\hrm-v060b1-fernet.key
if errorlevel 1 (
  echo ERROR: private key is not protected by .gitignore. Nothing will be pushed.
  exit /b 1
)

for /f "delims=" %%B in ('git branch --show-current') do set "HRM_CURRENT_BRANCH=%%B"
if /I not "%HRM_CURRENT_BRANCH%"=="%HRM_PILOT_BRANCH%" (
  echo ERROR: guarded push requires %HRM_PILOT_BRANCH% before validation.
  exit /b 1
)
git merge-base --is-ancestor %HRM_BASELINE_COMMIT% HEAD
if errorlevel 1 (
  echo ERROR: current RC branch is not based on the tested v0.8.0-rc.1 source revision.
  exit /b 1
)

echo Running mandatory %HRM_VERSION% isolated local gates before staging...
call "%~dp0APPLY-V100RC1.cmd"
if errorlevel 1 (
  echo ERROR: local %HRM_VERSION% gates failed. Nothing will be committed or pushed.
  exit /b 1
)

set "HRM_GATE_PYTHON=%CD%\.venv\Scripts\python.exe"
if not exist "%HRM_GATE_PYTHON%" (
  echo ERROR: isolated source-gate Python is missing after validation.
  exit /b 1
)

"%HRM_GATE_PYTHON%" ci\stage_v100rc1_overlay.py
if errorlevel 1 (
  echo ERROR: protected RC overlay staging failed. Nothing will be committed or pushed.
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

git commit -m "release: prepare final production candidate v1.0.0-rc.1"
if errorlevel 1 exit /b 1

git push -u origin %HRM_PILOT_BRANCH%
if errorlevel 1 exit /b 1

echo.
echo PASS: %HRM_VERSION% was pushed. GitHub must pass final production, Linux web, real-data, Windows install, and v0.8-to-v1.0-rc.1 upgrade gates.
exit /b 0
