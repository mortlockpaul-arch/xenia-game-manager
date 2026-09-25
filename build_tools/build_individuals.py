import filecmp
import logging
import shutil
import subprocess
import sys
import zipfile
from glob import escape
from pathlib import Path

from build_tools.tools import tools_setup
from config import get_app_dir, load_config, save_config
from logging_setup import setup_logger
from package_window import compress_folders, RAINBOW_COLORS

root = get_app_dir()
build_dir = root / "build"
current_folder = Path(__file__).resolve().parent

executables = [
    {
        "script": root / "main.py",
        "base": "gui",
        "target_name": "xenia-game-manager",
    },
    {
        "script": root / "main_updater.py",
        "base": "console",
        "target_name": "xenia-game-manager-updater",
    },
    # {
    #     "script": root / "archive_digital_window.py",
    #     "base": "console",
    #     "target_name": "xenia-game-manager-digital-downloader",
    # },
    # {
    #     "script": root / "archive_indie_window.py",
    #     "base": "console",
    #     "target_name": "xenia-game-manager-indie-downloader",
    # },
    # {
    #     "script": root / "archive_content_window.py",
    #     "base": "console",
    #     "target_name": "xenia-game-manager-content-downloader",
    # },
    # {
    #     "script": root / "xbox_unity_window.py",
    #     "base": "console",
    #     "target_name": "xenia-game-manager-unity-downloader",
    # },
    # {
    #     "script": root / "package_window.py",
    #     "base": "gui",
    #     "target_name": "xenia-game-rebuilder",
    # },
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
    log_message("Creating default game manager database and configuration files...", None)

    base_path = root

    db_dir = base_path / "database"
    config_dir = base_path / "config"

    backup_dir = base_path / "backup"
    backup_dir.mkdir(parents=True, exist_ok=True)

    db_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)

    def backup_existing(path: Path):
        if not path.exists():
            log_message(f"  No existing file to back up: {path.name}", None)
            return

        backup = backup_dir / path.name

        if backup.exists():
            log_message(f"  Removing old backup: {backup.name}", None)
            backup.unlink()

        log_message(f"  Backing up {path.name} -> {backup}", None)
        shutil.copy2(path, backup)

    config = load_config()
    config["game_manager_version"] = version
    save_config(config)
    log_message("Done.", None)

def copy_optimized_settings():
    settings_dest = root / "assets" / "settings"
    settings_source_dir = Path(r"C:\PycharmProjects\optimized-settings\settings")

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
            log_message(f"Copied: {dst}")

    if copied == 0:
        log_message("All optimized settings are already up to date.")
    else:
        log_message(f"Updated {copied} file(s).")

def cleanup_egg_info():
    for egg_info in current_folder.glob("*.egg-info"):
        shutil.rmtree(egg_info)
        log_message(f"Deleted: {egg_info}")

def build_executable(executable, version):
    from cx_Freeze import Executable, setup
    target_name = executable["target_name"] + f"-{version}"
    target_dir = build_dir / executable["target_name"]

    if target_dir.exists():
        shutil.rmtree(target_dir)

    print()
    print("=" * 70)
    print(f"Building {target_name}")
    print("=" * 70)

    setup(
        name=target_name,
        version=version,
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
                target_name=target_name,
            )
        ],
        script_args=["build_exe"],
    )

def zip_portable(executable, version):
    build_dir_current = Path(build_dir) / executable["target_name"]
    out_zip = Path(build_dir / "dist") / f"{executable['target_name']}-portable-{version}.zip"
    log_message(f"{build_dir_current}", None)
    log_message(f"{out_zip}", None)
    if out_zip.exists():
        out_zip.unlink()
        log_message(f"Deleting existing portable zip: {out_zip}", None)

    out_zip.parent.mkdir(exist_ok=True)

    # Add portable.txt to the root of the ZIP
    (build_dir_current / "portable.txt").touch()
    try:
        log_message(f"Compressing {build_dir_current} Folder", None)
        compress_folders(root, [build_dir_current], out_zip, False, log_callback=log_message)
        log_message(f"Compressed {build_dir_current} successfully", None)
    except Exception as e:
        log_message(f"Failed to compress {build_dir_current}: {type(e).__name__}: {e}", None)

    log_message(f"Portable zip created: {out_zip}", None)

def build_all(version):
    build_dir.mkdir(exist_ok=True)
    for executable in executables:
        build_executable(executable,version=version)
        zip_portable(executable,version=version)

# def build_portables(version):
#     build_dir.mkdir(exist_ok=True)
#     for executable in executables:
#         zip_portable(executable,version=version)
#     cleanup_egg_info()

def build_msi(version):
    from cx_Freeze import Executable, setup

    main_executable = Executable(
        script=str(root / "main.py"),
        base="gui",
        icon=str(icon),
        target_name="xenia-game-manager",
    )

    build_exe_options = {
        "packages": packages,
        "excludes": excludes,
        "include_files": [
            (str(source), destination)
            for source, destination in include_files
        ],
        "optimize": optimize,
        "build_exe": str(build_dir / f"xenia-game-manager-{version}"),
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
        name=f"Xenia Game Manager {version}",
        version=version,
        description="Xenia Game Manager",
        author="Paul Mortlock",
        options={
            "build_exe": build_exe_options,
            "bdist_msi": bdist_msi_options,
        },
        executables=[main_executable],
        script_args=["bdist_msi"],
    )

def log_message(message, color = None):
    logger_current = setup_logger()
    logger_current.info(f"{message}")

if __name__ == "__main__":
    current_version = "1.3.5"
    tools_setup()
    copy_optimized_settings()
    create_defaults(version=current_version)
    cleanup_egg_info()

    if len(sys.argv) > 1 and sys.argv[1].lower() == "msi":
        build_msi(version=current_version)
    if len(sys.argv) > 1 and sys.argv[1].lower() == "portables":
        build_all(version=current_version)
