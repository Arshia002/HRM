from pathlib import Path

root = Path(SPECPATH).parents[1]
src = root / "src"

a = Analysis(
    [str(root / "build" / "windows" / "entry_service.py")],
    pathex=[str(src)],
    binaries=[],
    datas=[(str(root / "data" / "seed" / "sazmanhr-seed.sqlite"), "data/seed")],
    hiddenimports=[
        "servicemanager", "win32service", "win32serviceutil", "win32event",
        "win32timezone", "pythoncom", "pywintypes",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="HRMService",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(root / "assets" / "HRM.ico"),
)
