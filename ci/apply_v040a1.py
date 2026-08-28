from __future__ import annotations
import subprocess
from pathlib import Path

BEGIN = "# BEGIN HRM V040A1 PRIVATE MIGRATION DATA"
END = "# END HRM V040A1 PRIVATE MIGRATION DATA"
RULES = """migration/input/*
!migration/input/.gitkeep
migration/output/*
!migration/output/.gitkeep
private-data/
*.migration.sqlite
normalized-private.json
"""

def in_git_repo(root: Path) -> bool:
    r = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=root, capture_output=True, text=True)
    return r.returncode == 0 and r.stdout.strip() == "true"

def merge_gitignore(root: Path) -> bool:
    path = root / ".gitignore"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if BEGIN in existing and END in existing:
        return False
    block = f"\n{BEGIN}\n{RULES}{END}\n"
    path.write_text(existing.rstrip() + block, encoding="utf-8")
    return True

def main() -> int:
    root = Path.cwd()
    if not in_git_repo(root):
        print("FAIL: current directory is not an HRM Git repository.")
        return 1
    changed = merge_gitignore(root)
    print("PASS: private migration Git rules " + ("added." if changed else "already present."))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
