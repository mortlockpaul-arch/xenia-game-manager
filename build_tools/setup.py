from pathlib import Path
from cx_Freeze import setup, Executable

root = Path(__file__).parent.parent

executables = [
    Executable(
        script=str(root / "src" / "main.py"),
        base="gui",
        icon=str(root / "src" / "assets" / "icons" / "app.ico"),
        target_name="Xenia Game Manager"
    ),
    Executable(
        script=str(root / "src" / "main_updater.py"),
        base=None,
        icon=str(root / "src" / "assets" / "icons" / "app.ico"),
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
        (str(root / "src" / "db"), "db"),
        (str(root / "src" / "config"), "config"),
        (str(root / "src" / "assets" / "icons"), "assets/icons"),
        (str(root / "src" / "assets" / "settings"), "assets/settings"),
        (str(root / "src" / "assets" / "zip"), "assets/zip"),
        (str(root / "src" / "assets" / "default"), "assets/default"),
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
        ("IconId", str(root / "src" / "assets" / "icons" / "app.ico")),
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
