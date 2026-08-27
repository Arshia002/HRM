@echo off
setlocal EnableExtensions
title HRM Diagnostics

set "OUT=%TEMP%\HRM-Diagnostics-%RANDOM%-%RANDOM%"
set "ZIP=%OUT%.zip"
mkdir "%OUT%" >nul 2>&1
if errorlevel 1 goto :denied

echo Collecting non-sensitive diagnostics...
systeminfo >"%OUT%\computer.txt" 2>&1
sc.exe query HRMCentral >"%OUT%\service.txt" 2>&1
sc.exe qc HRMCentral >>"%OUT%\service.txt" 2>&1
netstat.exe -ano | findstr.exe ":8765" >"%OUT%\port-8765.txt" 2>&1

if exist "%ProgramData%\HRM\server.json" copy /Y "%ProgramData%\HRM\server.json" "%OUT%\server.json" >nul 2>&1
if exist "%ProgramData%\HRM\logs\server.jsonl*" copy /Y "%ProgramData%\HRM\logs\server.jsonl*" "%OUT%\" >nul 2>&1
if exist "%ProgramData%\HRM\logs\setup-server.log" copy /Y "%ProgramData%\HRM\logs\setup-server.log" "%OUT%\" >nul 2>&1

set "HASHES=%OUT%\installed-hashes.txt"
for %%F in (
  "%ProgramFiles%\HRM\Client\HRM.exe"
  "%ProgramFiles%\HRM\Server\HRMServer.exe"
  "%ProgramFiles%\HRM\Server\HRMService.exe"
) do (
  if exist "%%~F" (
    echo %%~F>>"%HASHES%"
    certutil.exe -hashfile "%%~F" SHA256 >>"%HASHES%" 2>&1
  )
)

where tar.exe >nul 2>&1
if errorlevel 1 goto :folder_ready
tar.exe -a -c -f "%ZIP%" -C "%OUT%" . >nul 2>&1
if errorlevel 1 goto :folder_ready

echo.
echo Diagnostics ZIP created:
echo %ZIP%
echo The database, FIRST_LOGIN file, and passwords were not collected.
echo.
pause
exit /b 0

:folder_ready
echo.
echo Diagnostics folder created:
echo %OUT%
echo ZIP creation was unavailable, but the folder can be sent as-is.
echo The database, FIRST_LOGIN file, and passwords were not collected.
echo.
pause
exit /b 0

:denied
echo.
echo ERROR: Windows denied access to the temporary diagnostics folder.
echo Ask IT to check write access to: %TEMP%
echo.
pause
exit /b 1
