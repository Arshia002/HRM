from pathlib import Path

root = Path(SPECPATH).parents[1]
src = root / "src"

a = Analysis(
    [str(root / "build" / "windows" / "entry_client.py")],
    pathex=[str(src)],
    binaries=[],
    datas=[(str(root / "assets" / "HRM.png"), "assets")],
    hiddenimports=["PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="HRM",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(root / "assets" / "HRM.ico"),
)
