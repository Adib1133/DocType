# doctype.spec
# PyInstaller spec file for DocType – Image to Document
# Run with:  pyinstaller doctype.spec

import sys
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Collect all customtkinter assets (themes, images, fonts)
ctk_datas = collect_data_files("customtkinter", include_py_files=False)

a = Analysis(
    ["app.py"],
    pathex=["."],
    binaries=[],
    datas=[
        # CustomTkinter bundled assets (themes, images, fonts)
        *ctk_datas,
        # Our own processing module
        ("image_processor.py", "."),
        # Sample images (optional – comment out to reduce size)

    ],
    hiddenimports=[
        # CustomTkinter sub-packages
        *collect_submodules("customtkinter"),
        # PIL / Pillow
        "PIL._tkinter_finder",
        "PIL.Image",
        "PIL.ImageTk",
        "PIL.ImageEnhance",
        # OpenCV
        "cv2",
        # NumPy
        "numpy",
        # img2pdf
        "img2pdf",
        "pikepdf",
        "lxml",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["matplotlib", "scipy", "pandas", "jupyter"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DocType",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # no console window (GUI app)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon="icon.ico",      # uncomment and set path if you have an icon file
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="DocType",
)
