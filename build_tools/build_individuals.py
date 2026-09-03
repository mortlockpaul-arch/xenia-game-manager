import filecmp
import logging
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from build_tools.tools import tools_setup
from config import get_app_dir, load_config_file, save_config
from logging_setup import setup_logger

root = get_app_dir()
build_dir = root / "build"
current_folder = build_dir

executables = [
    {
        "script": root / "main.py",
        "base": "gui",
        "target_name": "xbox-game-manager",
    },
    {
        "script": root / "main_updater.py",
        "base": "console",
        "target_name": "xbox-game-manager-updater",
    },
    {
        "script": root / "archive_digital_window.py",
        "base": "console",
        "target_name": "xbox-game-manager-digital-downloader",
    },
    {
        "script": root / "archive_indie_window.py",
        "base": "console",
        "target_name": "xbox-game-manager-indie-downloader",
    },
    {
        "script": root / "archive_content_window.py",
        "base": "console",
        "target_name": "xbox-game-manager-content-downloader",
    },
    {
        "script": root / "xbox_unity_window.py",
        "base": "console",
        "target_name": "xbox-game-manager-unity-downloader",
    },
    {
        "script": root / "package_window.py",
        "base": "gui",
        "target_name": "xbox-game-rebuilder",
    },
]

packages = [
    "jaraco.text",
    "keyring",
    "keyring.backends.Windows",
    "win32ctypes",
]

excludes = [
    "tkinter",
    "unittest",
]

include_files = [
    (root / "database", "database"),
    (root / "config", "config"),
    (root / "assets", "assets"),
]

optimize = 2

icon = root / "assets" / "icons" / "app.ico"

def create_defaults(version):
    logger.info("Creating default game manager database and configuration files...")

    base_path = root

    db_dir = base_path / "database"
    config_dir = base_path / "config"

    backup_dir = base_path / "backup"
    backup_dir.mkdir(parents=True, exist_ok=True)

    db_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)

    def backup_existing(path: Path):
        if not path.exists():
            logger.info(f"  No existing file to back up: {path.name}")
            return

        backup = backup_dir / path.name

        if backup.exists():
            logger.info(f"  Removing old backup: {backup.name}")
            backup.unlink()

        logger.info(f"  Backing up {path.name} -> {backup}")
        shutil.copy2(path, backup)

    config = load_config_file()
    config["game_manager_version"] = version
    save_config(config)
    logger.info("Done.")

def copy_optimized_settings():
    settings_dest = root / "assets" / "settings"
    settings_source_dir = Path(r"C:\Users\mortl\Documents\GitHub\optimized-settings\settings")

    settings_dest.mkdir(parents=True, exist_ok=True)

    copied = 0

    for src in settings_source_dir.rglob("*"):
        if not src.is_file():
            continue

        dst = settings_dest / src.relative_to(settings_source_dir)
        dst.parent.mkdir(parents=True, exist_ok=True)

        if not dst.exists() or not filecmp.cmp(src, dst, shallow=False):
            shutil.copy2(src, dst)
            copied += 1
            logger.info(f"Copied: {dst}")

    if copied == 0:
        logger.info("All optimized settings are already up to date.")
    else:
        logger.info(f"Updated {copied} file(s).")

def cleanup_egg_info():
    for egg_info in current_folder.glob("*.egg-info"):
        shutil.rmtree(egg_info)
        logger.info(f"Deleted: {egg_info}")

def build_executable(executable):
    from cx_Freeze import Executable, setup

    target_dir = build_dir / executable["target_name"]

    if target_dir.exists():
        shutil.rmtree(target_dir)

    print()
    print("=" * 70)
    print(f"Building {executable['target_name']}")
    print("=" * 70)

    setup(
        name=executable["target_name"],
        version="1.2.4",
        description="Xbox Game Manager",
        options={
            "build_exe": {
                "build_exe": str(target_dir),
                "packages": packages,
                "excludes": excludes,
                "include_files": [
                    (str(source), destination)
                    for source, destination in include_files
                ],
                "optimize": optimize,
            }
        },
        executables=[
            Executable(
                script=str(executable["script"]),
                base=executable["base"],
                icon=str(icon),
                target_name=executable["target_name"],
            )
        ],
        script_args=["build_exe"],
    )

def zip_portable(executable):
    build_dir_current = Path(current_folder) / executable["target_name"]
    out_zip = Path(current_folder / "dist") / f"{executable['target_name']}-portable.zip"
    logger.info(f"{build_dir_current}")
    logger.info(f"{out_zip}")
    if out_zip.exists():
        out_zip.unlink()
        logger.info(f"Deleting existing portable zip: {out_zip}")

    out_zip.parent.mkdir(exist_ok=True)

    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zipf:
        for file in build_dir_current.rglob("*"):
            if file.is_file() and file.name != "portable.txt":
                zipf.write(file, file.relative_to(build_dir_current))

        # Add portable.txt to the root of the ZIP
        zipf.writestr("portable.txt", "")

    logger.info(f"Portable zip created: {out_zip}")

def build_all():
    build_dir.mkdir(exist_ok=True)
    for executable in executables:
        build_executable(executable)
        zip_portable(executable)
    cleanup_egg_info()

def build_portables():
    build_dir.mkdir(exist_ok=True)
    for executable in executables:
        zip_portable(executable)
    cleanup_egg_info()

def build_msi():
    from cx_Freeze import Executable, setup

    main_executable = Executable(
        script=str(root / "main.py"),
        base="gui",
        icon=str(icon),
        target_name="xbox-game-manager",
    )

    build_exe_options = {
        "packages": packages,
        "excludes": excludes,
        "include_files": [
            (str(source), destination)
            for source, destination in include_files
        ],
        "optimize": optimize,
        "build_exe": str(build_dir / "xbox-game-manager"),
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
                ("IconId", str(icon)),
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
        version="1.2.1",
        description="Xenia Game Manager",
        author="Xenia Game Manager",
        options={
            "build_exe": build_exe_options,
            "bdist_msi": bdist_msi_options,
        },
        executables=[main_executable],
        script_args=["bdist_msi"],
    )

if __name__ == "__main__":
    logger = setup_logger()
    if len(sys.argv) > 1 and sys.argv[1].lower() == "msi":
        build_msi()
    else:
        if len(sys.argv) > 1 and sys.argv[1].lower() == "portables":
            build_portables()
        else:
            build_all()
            create_defaults(version="1.2.4")
            tools_setup()
            copy_optimized_settings()