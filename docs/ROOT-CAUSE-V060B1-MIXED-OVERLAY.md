# HRM v0.6.0-beta.1 ci.5 — Mixed overlay prevention

## Observation

After extracting the ci.3 delivery over an existing working tree, the package
revision file contained ci.3 while a regression test still contained its ci.2
expectation. The guarded push correctly stopped, but only after the full test
suite ran.

## Process weakness

The local gate regenerated `PACKAGE-MANIFEST.json` before verifying the bytes
that had just been extracted. Regeneration could legitimize a partially
overwritten tree and defer detection until a later semantic test.

## Correction

`ci/validate_overlay_integrity.py` now runs before dependency installation and
before `tools/build_release.py`. It validates the package revision, path safety,
canonical byte length and SHA-256 of every declared payload file against the
original ZIP manifest. Extra protected files already present in the repository,
such as the encrypted data bundle and ignored local key, are not deleted.

`INSTALL-OVERLAY-V060B1.cmd` selects the pilot branch before installation,
forces `robocopy /IS /IT` to replace files even when Windows reports identical
size or timestamps, and validates the destination again. The guarded push now
only verifies the selected branch and never changes it after installation.

A regression creates a valid ci.5 overlay, verifies it, replaces one payload
with stale ci.4 content and proves the gate rejects the mixed tree immediately.
