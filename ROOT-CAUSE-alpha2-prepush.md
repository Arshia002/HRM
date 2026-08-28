# HRM v0.2.0-alpha.2 pre-push gate — root cause and correction

## Symptom

`APPLY-ALPHA2-FIX.cmd` stopped before commit with:

`Non-ASCII archive paths are forbidden in the CI package: docs/امنیت.md ...`

## Root cause

This was a **false positive in the new packaging gate**, not a failure of the
PyInstaller/Inno fix. `validate_archive_paths()` scanned the entire Git working
tree. The repository already contains historical Persian-named Markdown files.
Those files are not part of the alpha.2 CI overlay package and are not Inno
Setup sources, but the validator treated every repository path as an archive
payload path.

The alpha.2 ZIP itself used ASCII-safe filenames. The gate boundary was wrong.

## Correction

The gate now validates two real packaging boundaries separately:

1. Every `{#ProjectRoot}` source referenced by `HRM.iss` must be ASCII-safe and
   must exist.
2. Every file declared by `PACKAGE-MANIFEST.json` as part of the CI overlay must
   be ASCII-safe, relative, non-traversing, unique, and present after overlay.

Unrelated pre-existing repository documentation may retain Unicode filenames.
It is not copied into the installer or CI overlay artifact.

## Regression coverage

The unit suite now verifies that Persian-named repository docs are not included
in the CI overlay manifest while the package contract still passes.
