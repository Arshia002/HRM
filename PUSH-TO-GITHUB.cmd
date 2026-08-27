@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================================
echo   HRM v0.2.0-alpha.1 - Push CI Build Package
echo ============================================================
echo.
echo This script stages this candidate and pushes the branch:
echo   feat/native-v49-shell
echo.

git --version >nul 2>&1 || goto :nogit

git status || goto :fail

git switch -C feat/native-v49-shell || goto :fail
git add -A || goto :fail
git commit -m "build: prepare HRM v0.2.0-alpha.1 Windows CI candidate" || goto :commit_note
git push -u origin feat/native-v49-shell || goto :fail

echo.
echo PUSH COMPLETE.
echo Open:
echo https://github.com/Arshia002/HRM/actions
echo.
echo Wait for workflow: HRM - Windows Build and Install Test
echo If GREEN, download artifact: HRM-0.2.0-alpha.1-Tested-Setup
echo If RED, download artifact: HRM-0.2.0-alpha.1-Failure-Logs
echo.
pause
exit /b 0

:commit_note
echo.
echo Git could not create a new commit. If working tree is already clean,
echo push the branch manually with:
echo   git push -u origin feat/native-v49-shell
echo.
pause
exit /b 2

:nogit
echo ERROR: Git is not installed or is not on PATH.
pause
exit /b 10

:fail
echo.
echo ERROR: command failed. Review the output above. Nothing is Final yet.
pause
exit /b 1
