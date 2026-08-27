# HRM v0.2.0-alpha.1 CI Package — Local Validation

Status: **READY FOR WINDOWS CI**

This package is intentionally not marked as a Windows-tested Setup. It is the source/CI candidate that must be pushed to GitHub Actions.

## Local checks completed

- Python unit/integration/package/CI contract tests: **36 / 36 PASS**
- Python source compilation (`compileall`): **PASS**
- GitHub workflow YAML parse: **PASS**
- Native Qt/no browser-engine package rule: **PASS**
- Bootstrap secret unit test and forced-password-change behavior: **PASS**
- Installer script structural hardening tests: **PASS**

## Windows-only checks delegated to GitHub Actions

The included Windows workflow will build and then test:

- PyInstaller binaries
- Inno Setup output
- clean Full install
- Windows Service `HRMCentral`
- LocalSystem service identity
- Service SID ACL
- TLS/database/version health
- Desktop shortcut
- first login with project Bootstrap secret
- dashboard blocked until password change
- forced password change
- Bootstrap invalidation after password change
- in-place upgrade
- account/data/sentinel preservation through upgrade
- uninstall and service removal
- operational data preservation after uninstall

A release is not approved until the GitHub Actions run is GREEN and the resulting artifact is manually tested by the project owner.
