# HRM / SazmanHR Enterprise — Production Readiness Roadmap

**Purpose:** Governing roadmap from the current tested RC3 checkpoint to controlled organizational deployment.

**Project goal:** Deliver an offline Windows HRM system suitable for organizational use with:
- 6 administrator accounts with defined roles and enforced permissions
- the real organizational personnel dataset with an actual personnel row count of 1356
- Windows Service operation under SCM
- safe install, upgrade, rollback, uninstall, reinstall and reboot behavior
- verified backup/restore and interrupted-upgrade recovery
- auditable HR workflows
- a reproducible, hash-locked release artifact

## 1. Current engineering baseline

Reference source checkpoint:
- Git commit: `ceea1a9`
- Commit message: `fix: harden rc3 service and alpha4 database upgrade`
- Full automated regression at checkpoint: `215/215 PASS`
- Working tree at checkpoint: clean

Reference RC3 Windows evidence already observed:
- `HRMCentralService` RUNNING
- SCM PID matched the PID listening on port `8765`
- service ImagePath pointed to versioned runtime generation `svc-bcfcec0b060ba72c3b7f91e6`
- `/api/health` returned HTTP 200
- reported version: `1.0.0-rc.4`
- TLS: `true`
- migrated DB identity: `product_id=sazmanhr-enterprise`, `schema_generation=16`, `schema_version=9`
- SQLite integrity: `ok`
- foreign key errors: `0`

Reference official Windows artifact from the completed build:
- Installer: `HRM-Setup-x64.exe`
- SHA-256: `b71a80f8d6acf0d48f483f9f9a54eba9afe5e22018d63d29d29d48080d1dc1aa`

**Important:** This evidence does not equal production release approval. The remaining gates below are mandatory.

## 2. Non-negotiable execution rules

1. Git is the source of truth. No production-source change exists unless it is committed.
2. Every defect fix follows: reproduce -> regression test -> patch -> targeted test -> full test -> commit.
3. No release gate may be weakened to make a build pass.
4. No production-data operation is allowed without a verified backup and a defined restore path.
5. Synthetic/demo datasets are never accepted as evidence for real-data readiness.
6. `metadata.dataset_personnel_count=1356` is not evidence that 1356 personnel exist.
7. Real-data acceptance requires an actual SQL row count of exactly 1356 in the accepted target dataset.
8. Real personnel data must never be committed to Git.
9. Repeated operational checks must become version-controlled scripts; they must not remain as long manual CMD sequences.
10. A tested artifact is immutable. If the release artifact is rebuilt after acceptance, acceptance must be repeated for the rebuilt artifact.
11. Final release/tagging is blocked until every mandatory gate is PASS.
12. Unknown is not PASS.

## 3. Status vocabulary

- `PASS` — objective acceptance evidence exists.
- `FAIL` — acceptance criterion was tested and failed.
- `NOT-TESTED` — criterion has not yet been exercised.
- `BLOCKED` — cannot be tested because a prerequisite is missing.
- `N/A` — explicitly outside the approved release scope.

## 4. Gate plan

### G7 — Acceptance Contract
**Goal:** Freeze the definition of "ready for organizational deployment."

Required outputs:
- `docs/PRODUCTION-READINESS-ROADMAP.md`
- `docs/ACCEPTANCE-MATRIX.md`

PASS criteria:
- release scope is explicit
- required business workflows are explicit
- real-data criterion is explicit
- 6-admin criterion is explicit
- recovery/deployment/security criteria are explicit
- every mandatory criterion has an owner, evidence type and status

### G8 — Real Data 1356
**Goal:** Prove that the real organizational dataset can be validated and accepted without data loss.

Implemented acceptance components:
- `ci/validate_v060b1_real_data.py`
- `tests/test_v060b1_real_data_ci.py`
- `tools/real_data_migration/production.py`
- `tests/test_real_data_initial_provisioning.py`
- `tests/test_real_data_candidate_promotion.py`

Mandatory validation:
- actual `SELECT COUNT(*) FROM personnel` equals `1356`
- SQLite `PRAGMA integrity_check` equals `ok`
- `PRAGMA foreign_key_check` returns zero rows
- personnel-number uniqueness rules pass
- required relationship invariants pass
- unresolved orphan unit/position relationships are zero unless explicitly approved
- backup is created and hash-verified before migration/import
- migration/import is first exercised on a copy
- final accepted target is revalidated after migration/import
- report contains no personal names or sensitive HR data

Hard FAIL:
- actual personnel count is not 1356
- unresolved corruption
- foreign-key errors
- silent record loss
- unapproved duplicate identity/personnel number
- acceptance based only on metadata

Current evidence:
- protected real-data validator and regression contract exist in Git
- fresh public seed -> offline protected-data candidate is regression-tested (`365beb4`)
- candidate -> live database atomic promotion with verified rollback is regression-tested (`a5efda7`)
- actual protected execution proving SQL `COUNT(*) = 1356` is still blocked and must not be inferred from metadata or synthetic fixtures

### G9 — Six Administrators / RBAC / Concurrency
**Goal:** Prove that six independent administrators can use the system safely.

Required coverage:
- six independent test accounts
- login/session independence
- role-specific authorization
- explicit negative authorization tests
- audit actor correctness
- concurrent reads
- concurrent edits
- stale-write/conflict behavior
- no silent overwrite of a newer record
- service remains healthy during the acceptance workload

Current evidence:
- automated mixed-role acceptance for `2 Super Admin + 4 HR Admin` is committed at `c2edbc4`
- six pinned-TLS sessions, independent writes, positive/negative RBAC, audit attribution and stale-write rejection are covered
- the Windows SCM service itself has not yet been exercised under the six-admin acceptance workload; that evidence remains pending

### G10 — HR Business Workflow Acceptance
**Goal:** Prove that the software completes the real daily HR workflows required for v1.

Minimum workflow candidates:
1. personnel lookup
2. personnel detail view
3. approved personnel edit
4. unit/position assignment
5. personnel movement/transfer
6. movement/history review
7. role/permission enforcement
8. audit review
9. required report/export
10. import/reconciliation workflow if it is part of v1 scope

Current evidence:
- F-001 through F-008 are covered by the end-to-end HR workflow acceptance committed at `1966a68`
- the accepted scenario verifies assignment history, movement boundary, reversal, RBAC, audit-chain validity, SQLite integrity and zero FK errors
- report/export scope (F-009) remains a business-scope decision
- import/reconciliation inclusion in v1 (F-010) remains a business-scope decision even though monthly-import regression coverage already exists

### G11 — Backup / Restore / Failure Recovery
**Goal:** Prove that operational failure does not cause unrecoverable service or data state.

Required scenarios:
1. normal backup of accepted real dataset
2. restore onto an independent clean environment
3. post-restore validation of personnel, users, relationships and audit
4. injected upgrade failure after DB migration but before service transaction commit
5. injected failure after service ImagePath cutover but before final commit
6. installer/process termination at defined transaction boundaries
7. reboot/interruption recovery at defined transaction boundaries

PASS criteria:
- system converges to either the fully old consistent state or the fully new consistent state
- no half-migrated database is accepted
- old service is not restarted against an incompatible DB
- recovery state is persisted sufficiently to resume or restore safely
- post-recovery health, integrity and authorization checks pass

### G12 — Final Windows Artifact & Security Acceptance
**Goal:** Validate the exact artifact intended for deployment.

Mandatory final-artifact scenarios:
- clean install
- first start
- reboot
- supported-version upgrade
- DB migration
- upgrade failure rollback
- uninstall
- reinstall
- configured data-preservation behavior
- SCM PID equals listener PID for port 8765
- `/api/health` returns HTTP 200 and status OK
- TLS validation according to the chosen client trust model
- no new HRM-related SCM Event IDs `7000`, `7009`, `7034`, `7039`
- private-key/file ACL expectations pass
- server-side authorization tests pass
- code-signing/publisher-trust decision is explicitly closed before release

**Artifact rule:** The accepted artifact hash is the release artifact hash. Rebuild means retest.

### G13 — Controlled Pilot & Release
**Goal:** Use the accepted build in a controlled real environment before broad rollout.

Release blocker policy:
- P0 blockers: `0`
- P1 critical issues: `0`
- unexplained data loss: `0`
- unresolved integrity errors: `0`
- unresolved permission bypasses: `0`
- unrecoverable deployment failures: `0`

Only after G13 PASS:
- final version decision
- release commit
- approved tag
- release notes
- artifact hash publication
- admin guide
- recovery guide
- controlled rollout decision

## 5. Critical path

`G7 Acceptance Contract`
→ `G8 Real 1356 Data`
→ `G9 Six Admins`
→ `G10 HR Workflows`
→ `G11 Disaster Recovery`
→ `G12 Final Windows Artifact`
→ `G13 Controlled Pilot`

Work that does not close one of these gates requires explicit justification before it is started.

## 6. Release decision

The project is not production-approved while any mandatory G8–G13 criterion is `FAIL`, `BLOCKED` or `NOT-TESTED`.

Passing unit tests, successful builds, valid hashes, a running Windows Service, or successful synthetic-data upgrades are necessary evidence, but none of them alone authorizes organizational deployment.
