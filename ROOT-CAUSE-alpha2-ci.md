# Root Cause — HRM v0.2.0-alpha.2 GitHub CI failure

## Failure observed

The Windows runner stopped in the **Validate packaging contract** step before PyInstaller/Inno Setup. The failure artifact recorded:

```text
PACKAGE CONTRACT ERROR: Files declared in CI package manifest are missing after overlay:
['.pytest_cache/.gitignore', '.pytest_cache/CACHEDIR.TAG', '.pytest_cache/README.md',
 '.pytest_cache/v/cache/lastfailed', '.pytest_cache/v/cache/nodeids']
```

## Root cause

`PACKAGE-MANIFEST.json` was generated from a developer worktree and accidentally declared five local `.pytest_cache` files. Git correctly ignored those files, therefore a clean GitHub checkout could never contain them. The overlay was internally valid on the packaging machine but **not reproducible from Git**.

This is a package-boundary defect, not a Windows/PyInstaller defect. The CI gate correctly blocked the build before consuming more runner time.

## Corrective action in alpha.3

1. `.pytest_cache`, `__pycache__`, virtualenvs, coverage files, build output and other transient paths are hard-excluded by both `.gitignore` and `tools/build_release.py`.
2. Release packaging selects only stable, explicitly allowed overlay files.
3. `ci/validate_package_contract.py --require-git-tracked` proves every manifest path exists in Git's index, which models a clean checkout.
4. A regression test rejects ephemeral paths in the manifest.
5. A clean-checkout simulation is run against the final extracted ZIP before delivery.

## Additional regressions found proactively

While reviewing the failed candidate against the last proven Windows installer (`0.1.0-alpha.4`), three compatibility regressions were also found and corrected before the next CI run:

- service name had drifted from `HRMCentralService` to `HRMCentral`;
- the proven `service-stop-before-copy` upgrade safety path had been lost;
- the service account had drifted from low-privilege `NT AUTHORITY\LocalService` to LocalSystem.

The alpha.3 package restores these proven behaviors, plus the frozen Qt client smoke test and temporary-only seed handling, while retaining the new bootstrap password flow.
