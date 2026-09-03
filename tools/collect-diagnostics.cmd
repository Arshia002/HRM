@echo off
setlocal EnableExtensions
title HRM Privacy-Safe Diagnostics
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0collect-diagnostics.ps1"
if errorlevel 1 (
  echo ERROR: privacy-safe diagnostics collection failed.
  pause
  exit /b 1
)
pause
exit /b 0
