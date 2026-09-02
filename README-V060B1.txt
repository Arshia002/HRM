HRM v0.6.0-beta.1 - Protected Organizational Pilot Candidate
==============================================================

Baseline: v0.5.0-alpha.1 / 8e3eb3baecb46d2a0f964322584e668a6e926ce2

This package adds the protected real-data validation gate. It does not contain
the four private source workbooks or their encryption key.

Required order from the repository root:

  PREPARE-REAL-DATA-V060B1.cmd "C:\HRM-Private-Input"
  CONFIGURE-REAL-DATA-SECRET-V060B1.cmd
  PUSH-TO-GITHUB.cmd

The input directory must be outside the Git repository. The preparation step
creates only an authenticated encrypted bundle under ci\real-data and a local
ignored key under private-data. The key must never be committed.

Expected successful GitHub artifact:
  HRM-0.6.0-beta.1-Tested-Setup

Accept the artifact only after the protected real-data cycle and every Windows
install, service, TLS, ACL, login, upgrade, preservation and uninstall gate pass.
