# ROOT CAUSE — v0.7.0-rc.1 ci.3 GitHub RC hardening import failure

## Symptom
The full candidate validator completed 129/129 tests, but the separate GitHub
`rc-hardening` step failed before executing network or disaster-recovery logic.
`tests.test_rc_network_resilience` and `tests.test_rc_disaster_recovery` could not
import `sazmanhr` on a clean Windows runner.

## Root cause
`ci/validate_v070rc1_candidate.py` deliberately supplies both the repository root
and `src/` through `PYTHONPATH`. The workflow then launched a second, direct
`python -m unittest ...` command outside that controlled environment. A clean
GitHub runner therefore had no import path for the src-layout package.

## Correction in ci.4
`ci/validate_rc_hardening.py` is now the single isolated hardening runner. It
constructs the same explicit source environment before invoking the four focused
RC suites. The workflow calls this runner instead of raw unittest. A regression
test removes inherited `PYTHONPATH` and proves the runner can import the RC
network and DR modules on a clean environment.

No production logic, real-data contract, database schema, or beta baseline was
changed by this correction.
