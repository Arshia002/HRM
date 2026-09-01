# HRM v0.4.0-alpha.2 — Windows SQLite Lock Root Cause

## Evidence

- GitHub Actions run `33516987480` passed the complete package contract.
- The migration validation step failed before PyInstaller, Inno Setup, or the
  install/upgrade/uninstall smoke test started.
- The Windows traceback identified `WinError 32` while deleting temporary
  `hrm.sqlite` fixtures and `WinError 5` while atomically replacing a failed
  import with its verified backup.

## Root cause

Every application-owned SQLite connection was explicitly closed, but two
Windows-only races remained:

1. `TemporaryDirectory` attempted one immediate recursive deletion after a
   just-closed WAL database. Windows Defender or an indexing filter can retain
   a non-delete-sharing scan handle briefly, which turns cleanup into a test
   error even though the application connection is closed.
2. Automatic rollback attempted `os.replace` once. The same transient handle
   could deny the otherwise atomic replacement before the verified backup was
   restored.

## Durable correction

- Direct test connections use `contextlib.closing` and explicit commits.
- Migration workspaces retry cleanup for a maximum of two seconds and still
  fail if a real lock remains.
- Rollback retries only `PermissionError`, remains bounded to 20 attempts, and
  re-raises persistent access denial without deleting either source file.
- Regression tests cover transient recovery and persistent-lock fail-safe
  behavior.
- GitHub always writes `migration-validation.log` and uploads it on failure,
  so this step can no longer fail without a preserved traceback.

No personnel dataset, approved chart count, Enterprise schema, or frontend
payload was changed by this correction.
