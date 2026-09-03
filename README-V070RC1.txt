HRM v0.7.0-rc.1 ci.2 - Organizational Pilot Release Candidate

Baseline: immutable tested tag v0.6.0-beta.1 at a8b93c981603c58d0edaf3d999e088c7a674aa1b
Branch: feat/organizational-pilot-v070rc1

New mandatory gates:
- central release identity contract
- six simultaneous clients over pinned TLS
- disconnect/reconnect recovery
- certificate fingerprint mismatch rejection
- secondary-destination backup and disaster restore
- corrupt-backup rejection
- privacy-safe diagnostics without raw request/client/exception fields
- real Windows installer upgrade from v0.6.0-beta.1 to v0.7.0-rc.1
- unchanged protected real-data contract: 1356 / 590 / 185 / 1 and 536+32=568, page16=24

The existing v060b1 encrypted bundle and the SAME Fernet key/Environment secret are reused.
Do not regenerate real data merely because the application version changed.
