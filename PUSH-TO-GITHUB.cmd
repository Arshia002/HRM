@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================================
echo   HRM v0.2.0-alpha.2 - validate, commit and push
echo ============================================================
echo.

where git.exe >nul 2>&1 || goto :nogit
where python.exe >nul 2>&1 || goto :nopython

for /f "delims=" %%B in ('git branch --show-current 2^>nul') do set "BRANCH=%%B"
if /I not "%BRANCH%"=="feat/native-v49-shell" (
  echo ERROR: current branch is "%BRANCH%".
  echo Switch to feat/native-v49-shell before pushing this candidate.
  exit /b 11
)

call "%~dp0APPLY-ALPHA2-FIX.cmd"
if errorlevel 1 goto :fail

git add -A || goto :fail
git status || goto :fail
git commit -m "fix: repair HRM alpha.2 Windows packaging contract" || goto :commit_note
git push origin feat/native-v49-shell || goto :fail

echo.
echo PUSH COMPLETE.
echo Open: https://github.com/Arshia002/HRM/actions
echo Wait for workflow: HRM - Windows Build and Install Test
echo GREEN artifact: HRM-0.2.0-alpha.2-Tested-Setup
echo RED artifact:   HRM-0.2.0-alpha.2-Failure-Logs
exit /b 0

:commit_note
echo.
echo Git did not create a new commit. Review git status before pushing.
exit /b 2

:nogit
echo ERROR: Git is not installed or is not on PATH.
exit /b 10

:nopython
echo ERROR: Python is not installed or is not on PATH.
exit /b 12

:fail
echo.
echo ERROR: command failed. Do not treat this candidate as Final.
exit /b 1
