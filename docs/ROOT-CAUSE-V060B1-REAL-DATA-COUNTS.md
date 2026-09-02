# HRM v0.6.0-beta.1 ci.2 — Real-data reconciliation correction

## Failure observed on the protected Windows runner

The candidate, dependency and 114-test source gates passed. Protected
real-data validation then stopped with:

- `FIXED_POSITION_COUNT_MISMATCH`
- `NAMED_POSITION_COUNT_MISMATCH`

No installer was built and no production or persistent database was changed.

## Root cause

The beta.1 CI validator passed the approved chart counts to the workbook
reconciler. Those values describe the Enterprise chart page:

- 536 approved fixed posts
- 32 approved named posts
- 568 approved posts in total

They do not describe rows in the private named-position assignment workbook.
The approved private-source contract is different:

- 1356 unique personnel
- 590 county/unit enrichments
- 185 active named-position occupant assignments
- one retired type-0 assignment ignored with an audit warning

The earlier synthetic scale fixture incorrectly manufactured 568 assignment
rows, so it reproduced the validator's assumption instead of the real source
topology.

## Correction

The protected validator now checks the two domains independently:

1. Source workbook aggregates are reconciled as 1356/590/185/1.
2. The ephemeral Enterprise shadow database is validated separately as
   536/32/568 with page 16 equal to 24.
3. All 185 active assignment rows must match personnel and position codes in
   the production-shaped shadow target.
4. Apply, verified backup, byte-for-byte rollback and deterministic replay
   remain mandatory.

The exact-scale regression fixture now mirrors this structure and a dedicated
test prevents chart-capacity counts from being reused as workbook row counts.

## Release identity

The application remains `0.6.0-beta.1` because application code and the
installer were not the cause. The corrected delivery is package revision
`0.6.0-beta.1-ci.2`, which must be tested by a new GitHub Actions run before
the beta is considered Windows-tested.
