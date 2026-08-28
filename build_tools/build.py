import filecmp
import logging
import shutil
import subprocess
import sys
import uuid
import zipfile
from pathlib import Path

from build_tools.tools import tools_setup
from config import load_config_file, save_config, get_app_dir
from logging_setup import setup_logger

root = get_app_dir()
current_folder = Path(__file__).parent

def generate_guid():
    return str(uuid.uuid4())


def zip_portable():
    build_dir = Path(current_folder / "build") / "exe.win-amd64-3.14"
    out_zip = Path(current_folder / "dist") / "xenia-game-manager-portable.zip"
    if out_zip.exists():
        out_zip.unlink()
        logging.info(f"Deleting existing portable zip: {out_zip}")
    out_zip.parent.mkdir(exist_ok=True)

    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zipf:
        for file in build_dir.rglob("*"):
            if file.name == "portable.txt":
                continue
            zipf.write(file, file.relative_to(build_dir))
            # Add portable.txt to the root of the ZIP
        if not (build_dir / "portable.txt").exists():
            zipf.writestr("portable.txt", "")
    logging.info(f"portable zip created: {out_zip}")


def create_defaults(version):
    logging.info("Creating default game manager database and configuration files...")

    base_path = root

    db_dir = base_path / "database"
    config_dir = base_path / "config"

    backup_dir = base_path / "backup"
    backup_dir.mkdir(parents=True, exist_ok=True)

    db_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)

    def backup_existing(path: Path):
        if not path.exists():
            logging.info(f"  No existing file to back up: {path.name}")
            return

        backup = backup_dir / path.name

        if backup.exists():
            logging.info(f"  Removing old backup: {backup.name}")
            backup.unlink()

        logging.info(f"  Backing up {path.name} -> {backup}")
        shutil.copy2(path, backup)

    config = load_config_file()
    config["game_manager_version"] = version
    save_config(config)
    logging.info("Done.")

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
            logging.info(f"Copied: {dst}")

    if copied == 0:
        logging.info("All optimized settings are already up to date.")
    else:
        logging.info(f"Updated {copied} file(s).")


def copy_updater():
    settings_dest = root / "build_tools/build/exe.win-amd64-3.14"
    settings_source_dir = Path(r"C:\Users\mortl\PycharmProjects\xenia-game-manager-updater\build\exe.win-amd64-3.14")

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
            logging.info(f"Copied: {dst}")

    if copied == 0:
        logging.info("Updater is already up to date.")
    else:
        logging.info(f"Updated {copied} file(s).")

logger = setup_logger()

create_defaults(version="1.1.9")

tools_setup()

copy_optimized_settings()

# Build the executable
subprocess.run([sys.executable, "setup.py", "build_exe"], check=True)

# Build the MSI
subprocess.run([sys.executable, "setup.py", "bdist_msi"], check=True)

zip_portable()
