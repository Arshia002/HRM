HRM v0.8.0-rc.1-ci.1
=====================

Purpose
-------
Production-history candidate based on the tested v0.7.0-rc.1 source revision.
This source package produces two gated artifacts from one shared HRM core:

1) Windows organizational installer (primary production candidate)
2) Linux Web Test package (test-only, NOT FOR PRODUCTION)

Key v0.8 additions
------------------
- Historical personnel movements with effective date, order metadata and audit snapshots.
- Previous assignments are closed and retained; they are not overwritten.
- Organizational/status changes through the public API must use the movement workflow.
- 2 Super Admin (owner) / 4 HR Admin (admin) policy.
- Only Super Admin can hard-delete, restore, manage users/security, or reverse the latest movement.
- Native Windows UI exposes personnel movement history and movement registration.
- Linux Web Test serves a browser UI from the same API/business rules and supports Docker testing.
- GitHub gates a real v0.7.0-rc.1 -> v0.8.0-rc.1 Windows installer upgrade.

Security boundary
-----------------
Do not add raw HR Excel files, plaintext real-data exports, Fernet keys, operational databases,
or .env files to this package or GitHub. Protected real-data validation remains aggregate-only.
