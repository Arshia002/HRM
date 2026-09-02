# HRM protected real-data CI boundary

Only these generated files may be committed in this directory:

- `hrm-real-data-v060b1.enc`
- `hrm-real-data-v060b1.enc.sha256`

The envelope uses authenticated Fernet encryption. Its key must exist only in
the protected GitHub Environment secret `HRM_REAL_DATA_KEY`. Plain Excel/CSV
files, decrypted workspaces, normalized records, databases and keys are
forbidden.

Create the envelope from a directory outside the repository:

```cmd
PREPARE-REAL-DATA-V060B1.cmd "C:\HRM-Private-Input"
```
