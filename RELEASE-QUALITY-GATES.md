# HRM v0.6.0-beta.1 ci.5 Release Quality Gates

This is an executable release contract. Candidate validation, package
validation, guarded push and GitHub Actions enforce the corresponding controls.

## Immutable baseline

- Base tag: `v0.5.0-alpha.1`
- Base commit: `8e3eb3baecb46d2a0f964322584e668a6e926ce2`
- No organizational installation before a green GitHub Tested Setup artifact.

## Source and package

- Exact dependency pins and wheel-only installation.
- Full regression, migration and packaging contracts.
- Clean-checkout and clean-ZIP revalidation.
- SHA-256 manifest for every source payload file.
- No caches, local environments, raw workbooks, keys or plaintext databases.

## Protected real data

- Exactly four approved source profiles.
- Authenticated encryption before Git; key only in `HRM_REAL_DATA_KEY`.
- Temporary decryption only; no plaintext cache or artifact.
- Aggregate-only validation evidence.
- Private sources: 1356 personnel, 590 county/unit enrichments, 185 active named-position assignments and one ignored legacy type-0 row.
- Enterprise chart (independent of workbook row counts): 536 fixed + 32 named = 568 approved posts.
- Page-16 approved post count: 24.
- Zero reconciliation errors.
- Staging integrity, verified backup, apply, rollback and deterministic replay.

## Windows acceptance

- Four frozen executables and full native UI smoke.
- Clean install, TLS, LocalService, Service SID and ACL.
- Bootstrap login and forced password change.
- In-place upgrade with data preservation.
- Silent uninstall and durable diagnostics.

Any failed or missing gate blocks commit, push, artifact acceptance and pilot deployment.
