from pathlib import Path

root = Path(SPECPATH).parents[1]
src = root / "src"

a = Analysis(
    [str(root / "build" / "windows" / "entry_server.py")],
    pathex=[str(src)],
    binaries=[],
    datas=[(str(root / "data" / "seed" / "sazmanhr-seed.sqlite"), "data/seed")],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="HRMServer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    icon=str(root / "assets" / "HRM.ico"),
)
