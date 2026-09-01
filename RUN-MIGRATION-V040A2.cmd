@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if "%~1"=="" (
  echo Usage: RUN-MIGRATION-V040A2.cmd "D:\HRM-Private-Data" "D:\HRM-Migration-Output" "D:\HRM-Private-Backup" [database]
  exit /b 2
)
if "%~2"=="" (echo ERROR: private output directory is required.& exit /b 2)
if "%~3"=="" (echo ERROR: private backup directory is required.& exit /b 2)

set "INPUT=%~1"
set "OUTPUT=%~2"
set "BACKUP=%~3"
set "DATABASE=%~4"
if "%DATABASE%"=="" set "DATABASE=%ProgramData%\HRM-Kermanshah\hrm.sqlite"

set "MIGRATION=%~dp0build-output\dist\HRMMigration.exe"
if not exist "%MIGRATION%" set "MIGRATION=%ProgramFiles%\HRM\Server\HRMMigration.exe"
if not exist "%MIGRATION%" (
  echo ERROR: HRMMigration.exe was not found. Build or install v0.4.0-alpha.2 first.
  exit /b 3
)
if not exist "%DATABASE%" (echo ERROR: target database not found: %DATABASE%& exit /b 4)

echo [1/4] Read-only reconciliation and Enterprise preflight...
"%MIGRATION%" --input-dir "%INPUT%" --output-dir "%OUTPUT%" --expected-personnel 1356 --target-db "%DATABASE%" --expected-chart-fixed 536 --expected-chart-named 32 --expected-chart-total 568
if errorlevel 1 (
  echo REFUSED: dry run or target validation failed. No production data was changed.
  exit /b 10
)

echo [2/4] Review migration-summary.json and target-preflight.json in:
echo %OUTPUT%
set "CONFIRM="
set /p "CONFIRM=Type APPLY-TO-HRM to create a backup and apply: "
if /I not "%CONFIRM%"=="APPLY-TO-HRM" (
  echo Cancelled. No production data was changed.
  exit /b 11
)

net session >nul 2>&1
if errorlevel 1 (echo ERROR: run this CMD as Administrator.& exit /b 12)

set "SERVICE_WAS_RUNNING=0"
sc.exe query HRMCentralService | findstr /I "RUNNING" >nul 2>&1 && set "SERVICE_WAS_RUNNING=1"
set "SERVICE_TOOL=%ProgramFiles%\HRM\Server\HRMService.exe"
if "%SERVICE_WAS_RUNNING%"=="1" (
  echo [3/4] Stopping HRMCentralService...
  "%SERVICE_TOOL%" --wait 30 stop
  if errorlevel 1 (echo ERROR: service could not be stopped.& exit /b 13)
)

echo [4/4] Applying the verified import transaction...
"%MIGRATION%" --input-dir "%INPUT%" --output-dir "%OUTPUT%" --expected-personnel 1356 --apply-to-db "%DATABASE%" --backup-dir "%BACKUP%" --confirm-apply APPLY-TO-HRM --expected-chart-fixed 536 --expected-chart-named 32 --expected-chart-total 568
set "MIGRATION_RC=%ERRORLEVEL%"

if "%SERVICE_WAS_RUNNING%"=="1" (
  "%SERVICE_TOOL%" --wait 30 start
  if errorlevel 1 (
    echo ERROR: migration exit=%MIGRATION_RC%, and the service could not be restarted.
    exit /b 14
  )
)

if not "%MIGRATION_RC%"=="0" (
  echo ERROR: migration failed with exit code %MIGRATION_RC%. Verified rollback was requested.
  exit /b %MIGRATION_RC%
)
echo PASS: production-apply-summary.json was created in %OUTPUT%
exit /b 0
