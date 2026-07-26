from pathlib import Path
from cx_Freeze import setup, Executable

from config import get_app_dir

root = get_app_dir()

executables = [
    Executable(
        script=str(root / "main.py"),
        base="gui",
        icon=str(root  / "assets" / "icons" / "app.ico"),
        target_name="Xenia Game Manager"
    ),
    Executable(
        script=str(root  / "main_updater.py"),
        base="console",
        icon=str(root  / "assets" / "icons" / "app.ico"),
        target_name="Xenia Game Manager Updater"
    )
]

build_exe_options = {
    "packages": [
        "jaraco.text",
        "keyring",
        "keyring.backends.Windows",
        "win32ctypes",
    ],
    "excludes": ["tkinter", "unittest"],
    "include_files": [
        (str(root / "db"), "db"),
        (str(root / "config"), "config"),
        (str(root / "assets"), "assets"),
    ],
    "optimize": 2,
}

bdist_msi_options = {
    "upgrade_code": "{93BB1981-574E-4B8D-8C55-204B160218CE}",
    "add_to_path": False,
    "launch_on_finish": True,
    "initial_target_dir": r"C:\xenia-game-manager",
    "all_users": True,
    "output_name": "xenia-game-manager-win64.msi",
    "product_name": "Xenia Game Manager",
    "data": {
    "Icon": [
        ("IconId", str(root / "assets" / "icons" / "app.ico")),
    ],
    "Shortcut": [
        (
            "DesktopShortcut",
            "DesktopFolder",
            "Xenia Game Manager",
            "TARGETDIR",
            "[TARGETDIR]XeniaGameManager.exe",
            None,
            "Launch Xenia Game Manager",
            None,
            "IconId",
            0,
            None,
            "TARGETDIR",
        ),
        (
            "StartMenuShortcut",
            "ProgramMenuFolder",
            "Xenia Game Manager",
            "TARGETDIR",
            "[TARGETDIR]XeniaGameManager.exe",
            None,
            "Launch Xenia Game Manager",
            None,
            "IconId",
            0,
            None,
            "TARGETDIR",
        ),
    ],
},
}

setup(
    name="Xenia Game Manager",
    version="0.9.5",
    description="Xenia Game Manager",
    author="Xenia Game Manager",
    options={
        "build_exe": build_exe_options,
        "bdist_msi": bdist_msi_options,
    },
    executables=executables,
)

