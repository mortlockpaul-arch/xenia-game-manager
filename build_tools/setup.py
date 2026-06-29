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
        (str(ROOT / "src" / "config"), "config"),
        (str(ROOT / "assets" / "icons"), "assets/icons"),
        (str(ROOT / "src" / "assets" / "settings"), "assets/settings"),
    ],
    "optimize": 2,
}

bdist_msi_options = {
    "upgrade_code": "{93BB1981-574E-4B8D-8C55-204B160218CE}",
    "add_to_path": False,
    "launch_on_finish": True,
    "initial_target_dir": r"C:\xenia-game-manager",
    "all_users": True,
    "output_name": "XeniaGameManager-win64.msi",
    "product_name": "Xenia Game Manager",
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
    author="Xenia Game Manager",
    options={
        "build_exe": build_exe_options,
        "bdist_msi": bdist_msi_options,
    },
    executables=executables,
)