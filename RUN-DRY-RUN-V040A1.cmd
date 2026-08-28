@echo off
setlocal
if "%~1"=="" (
  echo Usage: RUN-DRY-RUN-V040A1.cmd "D:\HRM-Private-Data" ["D:\HRM-Migration-Output"]
  exit /b 2
)
set "INPUT=%~1"
set "OUTPUT=%~2"
if "%OUTPUT%"=="" set "OUTPUT=%TEMP%\HRM-Migration-v040a1"
python -m tools.real_data_migration --input-dir "%INPUT%" --output-dir "%OUTPUT%" --expected-fixed 535 --expected-named 32
set RC=%ERRORLEVEL%
echo Reports: %OUTPUT%
exit /b %RC%
