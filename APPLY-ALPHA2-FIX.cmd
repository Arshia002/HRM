@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================================
echo   HRM v0.2.0-alpha.2 ci.2 - apply CI build fix
echo ============================================================
echo.

where git.exe >nul 2>&1
if errorlevel 1 (
  echo ERROR: git.exe was not found.
  exit /b 1
)
where python.exe >nul 2>&1
if errorlevel 1 (
  echo ERROR: python.exe was not found.
  exit /b 1
)

rem Remove only files introduced by the failed alpha.1 overlay. Do NOT remove
rem historical Persian-named repository docs: they are outside the CI package
rem and installer payload and are intentionally ignored by the corrected gate.
git rm -f --ignore-unmatch "build/windows/SazmanHR.iss" "assets/SazmanHR.ico" "assets/SazmanHR.png" "HRM-ALPHA1-NOTES.md" "TEST-REPORT-HRM-v0.2.0-alpha.1.md" >nul 2>&1
git rm -f --ignore-unmatch "docs/#U0627#U0645#U0646#U06cc#U062a.md" "docs/#U0631#U0627#U0647#U0646#U0645#U0627#U06cc-#U0627#U0633#U062a#U0642#U0631#U0627#U0631.md" "docs/#U0631#U0627#U0647#U0646#U0645#U0627#U06cc-#U0633#U0627#U062e#U062a.md" "docs/#U0645#U0639#U0645#U0627#U0631#U06cc.md" "docs/#U0648#U0636#U0639#U06cc#U062a-#U062a#U062d#U0648#U06cc#U0644.md" "docs/#U0686#U06a9#U200c#U0644#U06cc#U0633#U062a-#U062a#U0633#U062a-Windows.md" >nul 2>&1

echo Running corrected fail-fast packaging contract...
python ci\validate_package_contract.py
if errorlevel 1 (
  echo.
  echo ERROR: alpha.2 ci.2 packaging contract failed. Do NOT commit or push.
  exit /b 1
)

echo.
echo PASS: alpha.2 ci.2 packaging contract is valid.
echo Existing Unicode repository docs are outside the installer/CI overlay boundary.
echo Review git status, then commit/push only if expected.
echo.
git status
exit /b 0
