# Build with: pyinstaller --clean packaging/streamfetch.spec

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all


ROOT = Path(SPECPATH).parent
ICON = ROOT / (
    "packaging/streamfetch.icns" if sys.platform == "darwin" else "packaging/streamfetch.ico"
)

datas = [
    (str(ROOT / "app.py"), "."),
    (str(ROOT / ".streamlit"), ".streamlit"),
    (str(ROOT / "docs/assets/streamfetch-mark.svg"), "docs/assets"),
]
binaries = []
hiddenimports = []
for package in ("streamlit", "yt_dlp", "mutagen", "webview"):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

a = Analysis(
    [str(ROOT / "src/streamfetch/desktop.py")],
    pathex=[str(ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="StreamFetch",
    console=False,
    icon=str(ICON),
)

if sys.platform == "darwin":
    app = BUNDLE(
        exe,
        name="StreamFetch.app",
        icon=str(ICON),
        bundle_identifier="com.mxweir.streamfetch",
        info_plist={
            "CFBundleDisplayName": "StreamFetch",
            "CFBundleShortVersionString": "1.2.0",
            "NSHighResolutionCapable": True,
        },
    )
