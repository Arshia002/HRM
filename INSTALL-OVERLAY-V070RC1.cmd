@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"

set "HRM_OVERLAY_SOURCE=%CD%"
for /f "delims=" %%B in ('python "%HRM_OVERLAY_SOURCE%\ci\release_identity.py" --print branch') do set "HRM_PILOT_BRANCH=%%B"
for /f "delims=" %%C in ('python "%HRM_OVERLAY_SOURCE%\ci\release_identity.py" --print baseline_commit') do set "HRM_BASELINE_COMMIT=%%C"
for /f "delims=" %%R in ('python "%HRM_OVERLAY_SOURCE%\ci\release_identity.py" --print package_revision') do set "HRM_PACKAGE_REVISION=%%R"

if "%~1"=="" (
  echo ERROR: repository path is required.
  echo Usage: INSTALL-OVERLAY-V070RC1.cmd "C:\path\to\HRM-repository"
  exit /b 1
)
for %%I in ("%~1") do set "HRM_REPOSITORY=%%~fI"

where git.exe >nul 2>&1 || (echo ERROR: git.exe not found.& exit /b 1)
where python.exe >nul 2>&1 || (echo ERROR: python.exe not found.& exit /b 1)
if not exist "%HRM_REPOSITORY%\.git" (
  echo ERROR: target is not an HRM Git repository: %HRM_REPOSITORY%
  exit /b 1
)

echo Validating the clean %HRM_PACKAGE_REVISION% source package...
python "%HRM_OVERLAY_SOURCE%\ci\validate_overlay_integrity.py" --root "%HRM_OVERLAY_SOURCE%"
if errorlevel 1 exit /b 1

for /f "delims=" %%B in ('git -C "%HRM_REPOSITORY%" branch --show-current') do set "HRM_CURRENT_BRANCH=%%B"
if /I not "%HRM_CURRENT_BRANCH%"=="%HRM_PILOT_BRANCH%" (
  echo ERROR: target repository must already be on %HRM_PILOT_BRANCH%.
  echo Current branch: %HRM_CURRENT_BRANCH%
  exit /b 1
)

git -C "%HRM_REPOSITORY%" diff --quiet
if errorlevel 1 (
  echo ERROR: tracked worktree changes prevent safe RC overlay installation.
  exit /b 1
)
git -C "%HRM_REPOSITORY%" diff --cached --quiet
if errorlevel 1 (
  echo ERROR: staged changes prevent safe RC overlay installation.
  exit /b 1
)
git -C "%HRM_REPOSITORY%" merge-base --is-ancestor %HRM_BASELINE_COMMIT% HEAD
if errorlevel 1 (
  echo ERROR: RC branch is not based on the tested v0.6.0-beta.1 baseline.
  exit /b 1
)

echo Installing verified RC payload by manifest, independent of file size and timestamps...
python "%HRM_OVERLAY_SOURCE%\ci\install_verified_overlay.py" --source "%HRM_OVERLAY_SOURCE%" --target "%HRM_REPOSITORY%"
if errorlevel 1 (
  echo ERROR: manifest-driven RC overlay installation failed.
  exit /b 1
)

echo Revalidating the installed repository overlay...
python "%HRM_REPOSITORY%\ci\validate_overlay_integrity.py" --root "%HRM_REPOSITORY%"
if errorlevel 1 (
  echo ERROR: installed overlay does not exactly match %HRM_PACKAGE_REVISION%.
  exit /b 1
)

echo.
echo PASS: complete %HRM_PACKAGE_REVISION% overlay installed on %HRM_PILOT_BRANCH%.
echo NEXT: restore the existing beta Fernet key into private-data if needed, then run PUSH-TO-GITHUB.cmd
exit /b 0
