# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for SoilSense Monitor.

Build with:
    pyinstaller SoilSense.spec

Output:
    dist/SoilSenseMonitor/        ← onedir bundle
        SoilSenseMonitor.exe
        _internal/                 ← Python runtime + bundled deps
        config.json, result.pkl
        assets/
"""
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# ── Data files bundled alongside the exe ────────────────────────────────
# Each tuple is (source-on-disk, destination-relative-to-bundle-root).
datas = [
    ("config.json",       "."),
    ("result.pkl",        "."),
    ("assets/app_icon.ico", "assets"),
    ("assets/leaflet",    "assets/leaflet"),
]

# ── Hidden imports — modules PyInstaller's static analysis can miss ─────
# keyring loads its OS-specific backend at runtime via importlib.
# anthropic / openai use lazy submodule imports for retries, types, etc.
hiddenimports = (
    # keyring backends for each platform we might run on
    [
        "keyring.backends.Windows",
        "keyring.backends.macOS",
        "keyring.backends.SecretService",
        "keyring.backends.kwallet",
        "keyring.backends.chainer",
        "keyring.backends.fail",
        "keyring.backends.null",
    ]
    + collect_submodules("anthropic")
    + collect_submodules("openai")
    + collect_submodules("PyQt6.QtWebEngineCore")
    + collect_submodules("PyQt6.QtWebEngineWidgets")
)

# Pull in pkg-shipped data files for libraries that need them
datas += collect_data_files("certifi")             # SSL CA bundle for HTTPS calls
datas += collect_data_files("anthropic")
datas += collect_data_files("openai")


block_cipher = None


a = Analysis(
    ["AppMain.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # ── Other Qt bindings — PyInstaller refuses to bundle two ─────
        # Anaconda often ships PyQt5/PySide alongside PyQt6; we use only PyQt6.
        "PyQt5",
        "PySide2",
        "PySide6",
        "shiboken2",
        "qt_material",
        # ── Unused PyQt6 submodules (saves ~50-100 MB) ────────────────
        "PyQt6.QtBluetooth",
        "PyQt6.QtMultimedia",
        "PyQt6.QtMultimediaWidgets",
        "PyQt6.QtQml",
        "PyQt6.QtQuick",
        "PyQt6.QtQuick3D",
        "PyQt6.QtQuickWidgets",
        "PyQt6.QtPdf",
        "PyQt6.QtPdfWidgets",
        "PyQt6.QtPositioning",
        "PyQt6.QtRemoteObjects",
        "PyQt6.QtSensors",
        "PyQt6.QtSerialPort",  # we use pyserial, not Qt's serial
        "PyQt6.QtSpatialAudio",
        "PyQt6.QtSql",
        "PyQt6.QtTest",
        # ── Heavy science / data libs pandas pulled in but we don't use ─
        "tensorflow",
        "torch",
        # NOTE: scipy is NEEDED — soil/dielectric.py uses scipy.signal.medfilt
        # and savgol_filter for permittivity extraction. Do not exclude.
        "sklearn",
        "IPython",
        "jupyter",
        "notebook",
        "pyarrow",          # pandas optional Parquet/Arrow backend
        "numba",            # JIT — pandas/numpy optional speedup
        "llvmlite",         # numba's backend
        "tables",           # HDF5 (PyTables) — pandas optional HDF backend
        "fsspec",           # filesystem abstraction — pandas optional
        "sqlalchemy",       # SQL — pandas optional
        # NOTE: openpyxl is NEEDED — ui/DataCollectPanel.py:_load_freq_file
        # calls pd.read_excel() on user-picked .xlsx files. The except clause
        # there is bare, so a missing openpyxl looks like "Error loading IDs"
        # with no traceback. Do not exclude.
        "lxml",             # XML — not used directly
        "botocore",         # AWS SDK — not used
        "boto3",
        "sphinx",           # docs builder
        "docutils",
        "babel",
        "pytest",           # testing
        "py",
        # ── Misc anaconda noise ───────────────────────────────────────
        "zmq",              # ZeroMQ — pulled in by jupyter ecosystem
        "tornado",
        "ipykernel",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SoilSenseMonitor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                      # UPX can break Qt; leave disabled
    console=False,                   # TEMP: enable console to see errors during debug
                                    # change back to False for release
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/app_icon.ico",
    # Restore pre-PyInstaller-6 layout: put bundled data + dlls in the same
    # folder as the .exe instead of an _internal/ subfolder. Lets the app's
    # relative paths (config.json, result.pkl, assets/) resolve trivially
    # via the os.chdir(dirname(sys.executable)) call in AppMain.py.
    contents_directory=".",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="SoilSenseMonitor",
)
