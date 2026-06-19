from cx_Freeze import setup, Executable
from pathlib import Path
from version import get_version

ROOT = Path(__file__).resolve().parent.parent

APP_NAME = "Xenia Game Manager"
VERSION = get_version()

base = "gui"

executables = [
    Executable(
        script=str(ROOT / "src" / "main.py"),
        base=base,
        icon=str(ROOT / "assets" / "icons" / "app.ico"),
        target_name=APP_NAME.replace(" ", ""),
    )
]

build_exe_options = {
    "packages": [],
    "excludes": ["tkinter", "unittest"],
    "include_files": [
        (str(ROOT / "src" / "db"), "db"),
        (str(ROOT / "assets"), "assets"),
    ],
    "optimize": 2,
}

bdist_msi_options = {
    "upgrade_code": "{6B29FC40-CA47-1067-B31D-00DD010662DA}",
    "add_to_path": False,
    "initial_target_dir": r"[ProgramFilesFolder]\%s" % APP_NAME,
    "output_name": "XeniaGameManager-win64.msi",
    "data": {
        "Icon": [
            ("IconId", str(ROOT / "assets" / "icons" / "app.ico")),
        ],
    },
}

setup(
    name=APP_NAME,
    version=VERSION,
    description=APP_NAME,
    options={
        "build_exe": build_exe_options,
        "bdist_msi": bdist_msi_options,
    },
    executables=executables,
)