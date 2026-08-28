# HRM 0.2.0-alpha.1 Windows CI failure — root cause

## Observed failure

GitHub Actions completed the PyInstaller pass but `build_windows.py` stopped with:

`PyInstaller output is incomplete: ...\build-output\dist\HRM.exe`

The service executable immediately before that point was built successfully.

## Primary root cause

`build/windows/client.spec` still declared:

`name="SazmanHR"`

PyInstaller therefore emitted `SazmanHR.exe`, while all downstream stages expected `HRM.exe`:

- `build_windows.py`
- Inno Setup `[Files]`
- Desktop/Start Menu shortcuts
- acceptance tests

The failure was deterministic: the client build succeeded under the wrong filename and the post-build contract correctly rejected the missing `HRM.exe`.

## Secondary latent failure found during review

The alpha.1 package contained ZIP-escaped documentation filenames such as `docs/#U...md`, while the Inno script referenced Persian source filenames directly. After fixing the executable name, Inno Setup would have been at risk of failing because those source files did not exist under the referenced names.

Alpha.2 replaces installer source filenames with stable ASCII names:

- `docs/deployment-guide-fa.md`
- `docs/windows-test-checklist-fa.md`

Persian Start Menu labels are retained; only build-time source paths are ASCII-safe.

## Fixes in alpha.2

1. `client.spec` now emits `HRM.exe`.
2. Installer script renamed to `build/windows/HRM.iss`.
3. Temporary preflight payload renamed `HRMServerPreflight.exe`.
4. Installer source docs use ASCII-safe paths.
5. New `ci/validate_package_contract.py` checks all PyInstaller output names before dependencies/build work starts.
6. `build_windows.py` validates each expected EXE immediately after each PyInstaller spec.
7. GitHub Actions runs the packaging-contract gate before the Windows build.
8. Failure diagnostics now include a frozen executable inventory and PyInstaller warning files.
9. Public CI data guard remains active: only the 36-record synthetic seed is permitted.

## Expected Windows outputs

- `build-output/dist/HRM.exe`
- `build-output/dist/HRMServer.exe`
- `build-output/dist/HRMService.exe`
- `build-output/installer/HRM-Setup-x64.exe`

The package is not considered Windows-tested until the GitHub Actions acceptance job is green.
