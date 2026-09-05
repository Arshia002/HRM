HRM v1.0.0-rc.1-ci.2 — Final Production Release Candidate

Purpose
-------
This is the final production release candidate before the organizational pilot approval.
It is NOT the v1.0.0 production tag yet. The exact GitHub-tested Windows installer must
complete the real 1-server + 6-client pilot before promotion.

Production profile
------------------
- Windows Server 2022, dedicated VM/server preferred
- 8 CPU cores / 32 GB RAM / 1 TB SSD-NVMe recommended
- Internal LAN only; no Internet dependency
- Static internal IP + internal DNS name
- TLS and certificate pinning
- 6 HR users: 2 Super Admin + 4 HR Admin
- Daily backup, 30 local copies, configurable secondary destination
- Personnel movement history is mandatory for organization/position changes

Release outputs
---------------
- GitHub Windows artifact: HRM-1.0.0-rc.1-Tested-Setup
- GitHub Linux test artifact: HRM-1.0.0-rc.1-Linux-Web-Test

Promotion rule
--------------
Do not rebuild a successful installer for delivery. Source commit, GitHub run, artifact,
installer SHA-256 and delivered binary must remain identical.
