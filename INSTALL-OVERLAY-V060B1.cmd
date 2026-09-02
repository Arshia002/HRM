@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"

set "HRM_OVERLAY_SOURCE=%CD%"
set "HRM_PILOT_BRANCH=feat/organizational-pilot-v060b1"

if "%~1"=="" (
  echo ERROR: repository path is required.
  echo Usage: INSTALL-OVERLAY-V060B1.cmd "C:\path\to\HRM-repository"
  exit /b 1
)
for %%I in ("%~1") do set "HRM_REPOSITORY=%%~fI"

where git.exe >nul 2>&1 || (echo ERROR: git.exe not found.& exit /b 1)
where python.exe >nul 2>&1 || (echo ERROR: python.exe not found.& exit /b 1)
where robocopy.exe >nul 2>&1 || (echo ERROR: robocopy.exe not found.& exit /b 1)
if not exist "%HRM_REPOSITORY%\.git" (
  echo ERROR: target is not an HRM Git repository: %HRM_REPOSITORY%
  exit /b 1
)

echo Validating the clean ci.5 source package...
python "%HRM_OVERLAY_SOURCE%\ci\validate_overlay_integrity.py" --root "%HRM_OVERLAY_SOURCE%"
if errorlevel 1 exit /b 1

for /f "delims=" %%B in ('git -C "%HRM_REPOSITORY%" branch --show-current') do set "HRM_CURRENT_BRANCH=%%B"
if /I "%HRM_CURRENT_BRANCH%"=="%HRM_PILOT_BRANCH%" goto branch_ready

git -C "%HRM_REPOSITORY%" diff --quiet
if errorlevel 1 (
  echo ERROR: tracked worktree changes prevent safe branch selection.
  echo Move to %HRM_PILOT_BRANCH% first or restore a clean checkout, then run this installer again.
  exit /b 1
)
git -C "%HRM_REPOSITORY%" diff --cached --quiet
if errorlevel 1 (
  echo ERROR: staged changes prevent safe branch selection.
  exit /b 1
)

git -C "%HRM_REPOSITORY%" show-ref --verify --quiet refs/heads/%HRM_PILOT_BRANCH%
if errorlevel 1 (
  git -C "%HRM_REPOSITORY%" switch -c %HRM_PILOT_BRANCH%
) else (
  git -C "%HRM_REPOSITORY%" switch %HRM_PILOT_BRANCH%
)
if errorlevel 1 (
  echo ERROR: could not select %HRM_PILOT_BRANCH% before overlay installation.
  exit /b 1
)

:branch_ready
echo Installing every verified overlay file, including same-size and same-time files...
robocopy "%HRM_OVERLAY_SOURCE%" "%HRM_REPOSITORY%" /E /IS /IT /COPY:DAT /R:2 /W:1 /NFL /NDL /NJH /NJS /NP
if errorlevel 8 (
  echo ERROR: overlay copy failed.
  exit /b 1
)

echo Revalidating the installed repository overlay...
python "%HRM_REPOSITORY%\ci\validate_overlay_integrity.py" --root "%HRM_REPOSITORY%"
if errorlevel 1 (
  echo ERROR: installed overlay does not exactly match the ci.5 package.
  exit /b 1
)

echo.
echo PASS: complete ci.5 overlay installed on %HRM_PILOT_BRANCH%.
echo NEXT: cd /d "%HRM_REPOSITORY%" and run PUSH-TO-GITHUB.cmd
exit /b 0
