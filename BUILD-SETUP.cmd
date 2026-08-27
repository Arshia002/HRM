@echo off
setlocal EnableExtensions
title HRM 0.1.0-alpha.2 Setup Builder

:start
cd /d "%~dp0"
if errorlevel 1 goto :folder_denied

set "BOOTSTRAP_LOG=%~dp0build-setup-bootstrap.log"
>"%BOOTSTRAP_LOG%" echo HRM 0.1.0-alpha.2 Setup Builder
if errorlevel 1 goto :folder_denied
>>"%BOOTSTRAP_LOG%" echo Started: %date% %time%
>>"%BOOTSTRAP_LOG%" echo Folder: %~dp0

echo.
echo ============================================================
echo   HRM 0.1.0-alpha.2 - Windows Setup Builder
echo ============================================================
echo.
echo The complete ZIP must be extracted before running this file.
echo This builder does not invoke PowerShell.
echo.

call :find_python
if defined PYEXE goto :python_ready

echo Python 3.11 x64 was not found. Trying winget...
>>"%BOOTSTRAP_LOG%" echo Python 3.11 x64 not found; trying winget.
where winget.exe >nul 2>&1
if errorlevel 1 goto :python_missing

winget.exe install --id Python.Python.3.11 --exact --silent --accept-package-agreements --accept-source-agreements
if errorlevel 1 goto :python_install_failed

call :find_python
if not defined PYEXE goto :python_refresh_required

:python_ready
>>"%BOOTSTRAP_LOG%" echo Python: %PYEXE% %PYARG%
echo Python found: %PYEXE% %PYARG%
echo Starting tested Windows build. This can take several minutes...
echo.

"%PYEXE%" %PYARG% "%~dp0build\windows\build_windows.py" --launch
set "BUILD_RC=%ERRORLEVEL%"
if not "%BUILD_RC%"=="0" goto :build_failed

echo.
echo ============================================================
echo Build completed successfully.
echo Setup was opened. If it is not visible, use:
echo %~dp0build-output\installer\HRM-Setup-x64.exe
echo ============================================================
>>"%BOOTSTRAP_LOG%" echo Build completed successfully: %date% %time%
echo.
pause
exit /b 0

:find_python
set "PYEXE="
set "PYARG="

where py.exe >nul 2>&1
if errorlevel 1 goto :find_direct_python
py.exe -3.11 -c "import sys,struct; assert sys.version_info[:2] == (3,11) and struct.calcsize('P') == 8" >nul 2>&1
if errorlevel 1 goto :find_direct_python
set "PYEXE=py.exe"
set "PYARG=-3.11"
exit /b 0

:find_direct_python
for %%P in (
  "%LocalAppData%\Programs\Python\Python311\python.exe"
  "%ProgramFiles%\Python311\python.exe"
  "%ProgramFiles(x86)%\Python311\python.exe"
) do (
  if exist "%%~P" (
    "%%~P" -c "import sys,struct; assert sys.version_info[:2] == (3,11) and struct.calcsize('P') == 8" >nul 2>&1
    if not errorlevel 1 (
      set "PYEXE=%%~P"
      exit /b 0
    )
  )
)
exit /b 0

:folder_denied
echo.
echo ERROR: This folder is not writable or cannot be entered.
echo Extract the complete ZIP to Desktop or C:\HRM-Source and run again.
echo Do not run BUILD-SETUP.cmd from inside the ZIP or Program Files.
echo.
pause
exit /b 10

:python_missing
>>"%BOOTSTRAP_LOG%" echo ERROR: winget is unavailable.
echo.
echo ERROR: Python 3.11 x64 and winget were not found.
echo Install Python 3.11 x64 from your approved organization source,
echo then run this file again.
goto :failed_common

:python_install_failed
>>"%BOOTSTRAP_LOG%" echo ERROR: winget could not install Python. Exit code: %ERRORLEVEL%
echo.
echo ERROR: Python installation was blocked or failed.
echo Ask IT to install Python 3.11 x64, then run this file again.
goto :failed_common

:python_refresh_required
>>"%BOOTSTRAP_LOG%" echo ERROR: Python installed but was not detected in this session.
echo.
echo Python was installed, but Windows has not refreshed its paths yet.
echo Close this window, sign out and back in, then run BUILD-SETUP.cmd again.
goto :failed_common

:build_failed
>>"%BOOTSTRAP_LOG%" echo ERROR: Build failed with exit code %BUILD_RC% at %date% %time%.
echo.
echo ============================================================
echo Build failed with exit code %BUILD_RC%.
echo The window will remain open. You can retry or close it yourself.
echo Send these files for diagnosis:
echo   %BOOTSTRAP_LOG%
echo   %~dp0build-output\build.log
echo ============================================================

:failed_common
echo.
echo Bootstrap log: %BOOTSTRAP_LOG%
echo.
choice /C RC /N /M "Press R to retry, or C to close: "
if errorlevel 2 exit /b 1
goto :start
