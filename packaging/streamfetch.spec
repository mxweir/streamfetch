# Build with: pyinstaller --clean packaging/streamfetch.spec

from PyInstaller.utils.hooks import collect_all


datas = [
    ("app.py", "."),
    (".streamlit", ".streamlit"),
    ("docs/assets/streamfetch-mark.svg", "docs/assets"),
]
binaries = []
hiddenimports = []
for package in ("streamlit", "yt_dlp", "mutagen", "webview"):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

a = Analysis(
    ["src/streamfetch/desktop.py"],
    pathex=["src"],
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
    icon=None,
)
