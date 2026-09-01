from pathlib import Path

root = Path(SPECPATH).parents[1]
src = root / "src"

a = Analysis(
    [str(root / "build" / "windows" / "entry_migration.py")],
    pathex=[str(root), str(src)],
    binaries=[],
    datas=[],
    hiddenimports=["openpyxl", "xlrd"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "PySide6"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="HRMMigration",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    icon=str(root / "assets" / "HRM.ico"),
)
