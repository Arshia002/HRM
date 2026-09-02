@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if "%~1"=="" (
  echo USAGE: PREPARE-REAL-DATA-V060B1.cmd "C:\path\outside\repo\approved-input"
  exit /b 2
)
if not exist "%~1\." (
  echo ERROR: input directory does not exist: %~1
  exit /b 1
)
where python.exe >nul 2>&1 || (echo ERROR: python.exe not found.& exit /b 1)

set "HRM_GATE_PYTHON=%CD%\.venv\Scripts\python.exe"
if not exist "%HRM_GATE_PYTHON%" (
  python -m venv .venv || exit /b 1
)
"%HRM_GATE_PYTHON%" -m pip install --disable-pip-version-check --only-binary=:all: -r ci\requirements-source-gates.txt || exit /b 1

"%HRM_GATE_PYTHON%" ci\prepare_real_data_bundle.py --input-dir "%~1" || exit /b 1
echo.
echo PASS: encrypted bundle created under ci\real-data.
echo PRIVATE KEY: private-data\hrm-v060b1-fernet.key
echo Never commit, email or paste the private key into source files.
exit /b 0
