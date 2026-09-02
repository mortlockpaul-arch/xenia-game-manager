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

def generate_guid():
    return str(uuid.uuid4())



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


# Build the executable
subprocess.run([sys.executable, "setup.py", "build_exe"], check=True)

# Build the MSI
subprocess.run([sys.executable, "setup.py", "bdist_msi"], check=True)


