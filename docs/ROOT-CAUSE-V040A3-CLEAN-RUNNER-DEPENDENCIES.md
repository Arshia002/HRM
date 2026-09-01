# HRM v0.4.0-alpha.3 — Clean Runner Dependency Root Cause

## Exact failure

The preserved `migration-validation.log` from the second Windows run showed
two deterministic errors before PyInstaller started:

- `ModuleNotFoundError: No module named 'openpyxl'` while importing the
  Enterprise migration test module.
- `ModuleNotFoundError: No module named 'cryptography'` while the dry-run CLI
  imported the Enterprise repository/security layer.

The package contract passed. The workflow itself was wrong: migration tests
ran on the clean `actions/setup-python` interpreter before any project Python
requirements were installed. The later Windows builder would have installed
them in its own virtual environment, but that step was never reached.

## Correction

1. `ci/requirements-source-gates.txt` defines the exact minimal distributions
   needed before source validation: cryptography, openpyxl and xlrd.
2. Every source-gate pin must exactly match the corresponding full Windows
   build pin; drift fails before tests.
3. GitHub installs this file with wheel-only mode before migration validation
   and retains the complete installation log in both success and failure
   artifacts.
4. `APPLY-V040A3.cmd` creates an isolated `.venv`, installs the same file and
   runs every gate with that interpreter.
5. Inno Setup installation now happens after source validation, so dependency
   and source failures stop early without spending time on installer tooling.

## Boundary

This correction changes CI/bootstrap sequencing only. It does not change the
1356-person reconciliation result, the Enterprise database schema, private
data handling, or the approved 536 fixed + 32 named = 568 position contract.
