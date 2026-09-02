# HRM v0.6.0-beta.1 ci.3 — Deterministic aggregate privacy validation

## Failure

The protected data gate, package contract and candidate gate passed on `main`.
During the later build regression, the aggregate-only evidence test failed
because the short fixture value `111` appeared by chance inside an encrypted
bundle SHA-256 digest.

## Root cause

The test searched the raw serialized JSON for short private fixture values.
Cryptographic digests are intentionally pseudo-random hexadecimal strings, so
any short numeric sequence can eventually occur in a valid digest. The test
therefore had a probabilistic false-positive path even though no raw identifier
was present in the report.

## Correction

- JSON evidence is parsed structurally.
- Human-visible string fields are scanned for fixture PII.
- Fields ending in `_sha256` are excluded from the PII substring scan and are
  instead required to be exactly 64 lowercase hexadecimal characters.
- A regression deliberately embeds `111` in a valid digest and proves it is
  accepted.
- The same regression places `111` in a normal report field and proves the
  privacy scan still detects it.

Application behavior and the real-data contract are unchanged. This is package
revision `0.6.0-beta.1-ci.3`.
