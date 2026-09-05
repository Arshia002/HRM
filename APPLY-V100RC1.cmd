@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo [HRM] v1.0.0-rc.1 final production release-candidate gates

where git.exe >nul 2>&1 || (echo FAIL: git not found.& exit /b 1)
where python.exe >nul 2>&1 || (echo FAIL: python not found.& exit /b 1)
git rev-parse --is-inside-work-tree >nul 2>&1 || (echo FAIL: run from the HRM Git repository root.& exit /b 1)

echo Validating extracted RC overlay integrity before any regeneration...
python ci\validate_overlay_integrity.py || exit /b 1

set "HRM_GATE_PYTHON=%CD%\.venv\Scripts\python.exe"
if not exist "%HRM_GATE_PYTHON%" (
  echo Creating isolated source-gate environment...
  python -m venv .venv || exit /b 1
)

echo Installing exact source-gate dependencies...
"%HRM_GATE_PYTHON%" -m pip install --disable-pip-version-check --only-binary=:all: -r ci\requirements-source-gates.txt || exit /b 1

echo Regenerating package manifest from the current protected RC overlay...
"%HRM_GATE_PYTHON%" tools\build_release.py || exit /b 1
"%HRM_GATE_PYTHON%" ci\validate_v100rc1_candidate.py || exit /b 1
"%HRM_GATE_PYTHON%" ci\validate_package_contract.py || exit /b 1
echo PASS: HRM v1.0.0-rc.1 local quality gates passed.
exit /b 0
