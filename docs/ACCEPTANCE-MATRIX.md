# HRM / SazmanHR Enterprise — Acceptance Matrix

This matrix is the management contract for organizational deployment.

## Status legend
- `PASS`
- `FAIL`
- `NOT-TESTED`
- `BLOCKED`
- `N/A`

## A. Source, Build and Regression

| ID | Requirement | Current status | Evidence / PASS criterion | Owner |
|---|---|---|---|---|
| A-001 | Clean Git checkpoint exists | PASS | commit `ceea1a9` | Technical lead |
| A-002 | Full regression passes at checkpoint | PASS | 215/215 tests PASS | Technical lead |
| A-003 | Working tree clean at checkpoint | PASS | `git status --short` empty | Technical lead |
| A-004 | Official Windows build completes | PASS | official builder completed | Technical lead |
| A-005 | Package contract passes | PASS | package contract PASS | Technical lead |
| A-006 | Final release artifact built from final accepted source | NOT-TESTED | final RC build | Technical lead |
| A-007 | Final release artifact hash locked | NOT-TESTED | SHA-256 recorded | Technical lead |

## B. Windows Service and Runtime

| ID | Requirement | Current status | Evidence / PASS criterion | Owner |
|---|---|---|---|---|
| B-001 | Service runs under SCM | PASS | `HRMCentralService` RUNNING observed | Technical lead / IT |
| B-002 | SCM PID equals port 8765 listener PID | PASS | observed on RC3 run | Technical lead |
| B-003 | Runtime uses immutable/versioned generation path | PASS | ImagePath contained `svc-bcfcec0b060ba72c3b7f91e6` | Technical lead |
| B-004 | Health endpoint returns HTTP 200 / status OK | PASS | observed on RC3 | Technical lead |
| B-005 | TLS enabled | PASS | health reported `tls=true` | Technical lead |
| B-006 | No HRM SCM 7000/7009/7034/7039 in final acceptance window | NOT-TESTED | zero matching events | Technical lead / IT |
| B-007 | Reboot preserves healthy service state | NOT-TESTED | reboot + service/health checks | IT |

## C. Database Upgrade and Identity

| ID | Requirement | Current status | Evidence / PASS criterion | Owner |
|---|---|---|---|---|
| C-001 | Supported alpha.4 lineage recognized fail-closed | PASS | exact legacy identity/history tests | Technical lead |
| C-002 | alpha.4 schema 5 upgrades to current schema 9 | PASS | automated + real RC3 upgrade evidence | Technical lead |
| C-003 | DB promoted to current product/generation | PASS | product `sazmanhr-enterprise`, generation `16` observed | Technical lead |
| C-004 | Post-upgrade integrity check | PASS | `integrity_check=ok` observed | Technical lead |
| C-005 | Post-upgrade FK check | PASS | zero FK errors observed | Technical lead |
| C-006 | DB rollback path exists and is regression-tested | PASS | rollback tests | Technical lead |
| C-007 | Interrupted upgrade recovery across process termination/reboot | NOT-TESTED | G11 scenarios PASS | Technical lead / IT |

## D. Real Organizational Data — 1356 Personnel

| ID | Requirement | Current status | Evidence / PASS criterion | Owner |
|---|---|---|---|---|
| D-001 | Authoritative real-data source identified | BLOCKED | source owner/path/hash recorded privately | Project owner / HR |
| D-002 | Actual real personnel row count equals 1356 | BLOCKED | actual SQL count = 1356 | HR / Technical lead |
| D-003 | Dataset is not synthetic/demo | BLOCKED | provenance confirmed | HR |
| D-004 | Real-data validator exists in Git | NOT-TESTED | validator + tests committed | Technical lead |
| D-005 | Verified pre-migration backup exists | NOT-TESTED | backup hash + integrity verification | Technical lead |
| D-006 | Migration/import first succeeds on a copy | NOT-TESTED | sanitized report PASS | Technical lead |
| D-007 | Final target still contains exactly 1356 personnel | NOT-TESTED | post-operation SQL count = 1356 | Technical lead / HR |
| D-008 | No unresolved FK errors | NOT-TESTED | zero FK errors | Technical lead |
| D-009 | No unapproved duplicate personnel identifiers | NOT-TESTED | validator PASS | HR / Technical lead |
| D-010 | Unit/position relationship invariants pass | NOT-TESTED | validator + HR review | HR |
| D-011 | Sanitized acceptance report contains no sensitive personnel data | NOT-TESTED | report inspection | Project owner |

**Explicit non-evidence:** the previously inspected 36-row database is synthetic/demo and must never satisfy D-001 through D-010.

## E. Six Administrators / Authentication / Authorization

| ID | Requirement | Current status | Evidence / PASS criterion | Owner |
|---|---|---|---|---|
| E-001 | Six intended admin roles/accounts defined | NOT-TESTED | approved role/account matrix | Project owner / HR / IT |
| E-002 | Six independent concurrent sessions work | NOT-TESTED | acceptance test PASS | Technical lead |
| E-003 | Allowed actions succeed per role | NOT-TESTED | positive RBAC tests PASS | Technical lead |
| E-004 | Forbidden actions fail per role | NOT-TESTED | negative RBAC tests PASS | Technical lead |
| E-005 | Authorization enforced server-side | NOT-TESTED | API denial tests PASS | Technical lead |
| E-006 | Audit actor is correct for each admin | NOT-TESTED | audit assertions PASS | Technical lead |
| E-007 | Concurrent edit conflict is controlled | NOT-TESTED | no silent overwrite | Technical lead |
| E-008 | Service remains healthy under six-admin workload | NOT-TESTED | health + integrity PASS | Technical lead |

## F. HR Business Workflows

| ID | Requirement | Current status | Evidence / PASS criterion | Owner |
|---|---|---|---|---|
| F-001 | Personnel lookup workflow | NOT-TESTED | end-to-end scenario PASS | HR |
| F-002 | Personnel detail workflow | NOT-TESTED | end-to-end scenario PASS | HR |
| F-003 | Personnel edit workflow | NOT-TESTED | authorized edit + audit PASS | HR |
| F-004 | Unit/position assignment workflow | NOT-TESTED | relationship/history PASS | HR |
| F-005 | Personnel movement/transfer workflow | NOT-TESTED | movement + resulting state PASS | HR |
| F-006 | Movement/history review | NOT-TESTED | history complete/correct | HR |
| F-007 | Permission-aware workflow behavior | NOT-TESTED | allowed/denied actions match matrix | HR / Technical lead |
| F-008 | Audit review workflow | NOT-TESTED | actor/action/time/object correct | HR / Technical lead |
| F-009 | Required report/export workflow | BLOCKED | v1 report scope approved | HR |
| F-010 | Import/reconciliation workflow, if in v1 | BLOCKED | v1 scope decision | HR / Project owner |

## G. Backup, Restore and Disaster Recovery

| ID | Requirement | Current status | Evidence / PASS criterion | Owner |
|---|---|---|---|---|
| G-001 | Backup of accepted real dataset succeeds | NOT-TESTED | verified backup created | IT / Technical lead |
| G-002 | Restore onto independent clean environment succeeds | NOT-TESTED | restored system starts and validates | IT / Technical lead |
| G-003 | Restored personnel count/integrity/FKs match source | NOT-TESTED | validator PASS | Technical lead |
| G-004 | Restored users/roles/audit are correct | NOT-TESTED | assertions PASS | Technical lead |
| G-005 | Failure after DB migration before commit recovers safely | NOT-TESTED | injected failure PASS | Technical lead |
| G-006 | Failure after ImagePath cutover before commit recovers safely | NOT-TESTED | injected failure PASS | Technical lead |
| G-007 | Installer/process termination at boundary recovers safely | NOT-TESTED | interruption test PASS | Technical lead / IT |
| G-008 | Reboot/interruption recovery is deterministic | NOT-TESTED | old or new consistent state only | IT / Technical lead |
| G-009 | Recovery procedure documented | NOT-TESTED | guide reviewed | IT |

## H. Security and Operational Controls

| ID | Requirement | Current status | Evidence / PASS criterion | Owner |
|---|---|---|---|---|
| H-001 | TLS is enabled | PASS | current health evidence | Technical lead |
| H-002 | Client certificate trust behavior is defined and tested | NOT-TESTED | validation behavior PASS | IT / Technical lead |
| H-003 | Private key/file ACLs meet policy | NOT-TESTED | ACL test PASS | IT |
| H-004 | Certificate renewal/replacement procedure exists | NOT-TESTED | documented/rehearsed | IT |
| H-005 | Code-signing/publisher-trust decision closed | BLOCKED | signed artifact or documented exception | Project owner / IT |
| H-006 | Sensitive data excluded from Git and sanitized reports | NOT-TESTED | repository/report inspection | Project owner |

## I. Installer Lifecycle — Final Artifact

| ID | Requirement | Current status | Evidence / PASS criterion | Owner |
|---|---|---|---|---|
| I-001 | Fresh install PASS | NOT-TESTED | final artifact on clean Windows | IT / Technical lead |
| I-002 | First start PASS | NOT-TESTED | service + health PASS | Technical lead |
| I-003 | Reboot PASS | NOT-TESTED | auto-start + health PASS | IT |
| I-004 | Supported upgrade PASS | PARTIAL | alpha.4->RC3 observed; repeat on final artifact | Technical lead |
| I-005 | Failed upgrade rollback PASS | NOT-TESTED | failure injection + old-state health | Technical lead |
| I-006 | Uninstall PASS | NOT-TESTED | no unsafe residue | IT / Technical lead |
| I-007 | Data-preservation policy on uninstall PASS | NOT-TESTED | approved behavior | Project owner / IT |
| I-008 | Reinstall PASS | NOT-TESTED | operational state PASS | IT |
| I-009 | Exact accepted artifact hash retained | NOT-TESTED | deployed hash equals accepted hash | IT |

## J. Controlled Pilot and Release

| ID | Requirement | Current status | Evidence / PASS criterion | Owner |
|---|---|---|---|---|
| J-001 | Controlled pilot environment approved | NOT-TESTED | pilot plan approved | Project owner / IT / HR |
| J-002 | Accepted real dataset loaded | BLOCKED | G8 PASS | HR / Technical lead |
| J-003 | Intended admin accounts/roles active | BLOCKED | G9 PASS | IT / HR |
| J-004 | Backup/recovery procedure available | BLOCKED | G11 PASS | IT |
| J-005 | Pilot has zero P0 blockers | NOT-TESTED | issue register | Project owner |
| J-006 | Pilot has zero unresolved P1 critical issues | NOT-TESTED | issue register | Project owner |
| J-007 | No unexplained data loss/integrity error | NOT-TESTED | acceptance evidence | Technical lead / HR |
| J-008 | No unresolved permission bypass | NOT-TESTED | security acceptance evidence | Technical lead |
| J-009 | Final release commit/tag created only after mandatory gates PASS | BLOCKED | G8-G13 complete | Technical lead / Project owner |

## Gate Summary

| Gate | Status |
|---|---|
| G7 Acceptance Contract | READY FOR REVIEW |
| G8 Real Data 1356 | BLOCKED |
| G9 Six Admins / RBAC / Concurrency | NOT-TESTED |
| G10 HR Business Workflows | NOT-TESTED |
| G11 Backup / Restore / Recovery | NOT-TESTED |
| G12 Final Windows & Security Acceptance | NOT-TESTED |
| G13 Controlled Pilot & Release | BLOCKED |

## Approval rule

No final organizational deployment is authorized while a mandatory row in sections D through J is `FAIL`, `BLOCKED`, `NOT-TESTED` or otherwise unresolved.
