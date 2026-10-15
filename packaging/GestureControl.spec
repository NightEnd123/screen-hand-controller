# PyInstaller spec for GestureControl.exe (one-folder build). Run via build.ps1.
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

import mediapipe

ROOT = Path(SPECPATH).parent
MP = Path(mediapipe.__file__).parent

datas = [
    (str(ROOT / "models" / "hand_landmarker.task"), "models"),
    (str(ROOT / "gesture_control" / "default_config.toml"), "gesture_control"),
    (str(ROOT / "LICENSE"), "."),
    (str(ROOT / "THIRD_PARTY_NOTICES.md"), "."),
    # mediapipe finds its native library through importlib.resources at this package path
    (str(MP / "tasks" / "c" / "libmediapipe.dll"), "mediapipe/tasks/c"),
]
datas += collect_data_files("mediapipe", excludes=["**/test/**", "**/testdata/**", "**/*.dll"])

hiddenimports = collect_submodules("mediapipe.tasks.python", filter=lambda m: ".test" not in m)
hiddenimports += ["mediapipe.tasks.c", "pystray._win32", "PIL.ImageTk"]

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT)],
    datas=datas,
    hiddenimports=hiddenimports,
    # LGPL libraries stay as plain, replaceable .py files rather than packed into the archive
    module_collection_mode={"pynput": "py", "pystray": "py"},
    excludes=["pytest", "IPython", "jax", "tensorflow", "torch", "pandas", "scipy"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="GestureControl",
    icon=str(ROOT / "packaging" / "icon.ico"),
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="GestureControl", upx=False)
