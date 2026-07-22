import argparse
import logging
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import ui
from config import get_app_dir, load_config, save_config
from extract import extract_archives


def wait_for_process(pid: int, timeout: int = 30):
    """Wait for the main application to exit."""


    try:
        import psutil

        while timeout > 0:
            if not psutil.pid_exists(pid):
                return
            logging.info(f"Waiting for process {pid}...{timeout}")
            time.sleep(1)
            timeout -= 1
    except ImportError:
        # Fallback if psutil isn't installed
        time.sleep(5)


def copy_files(source: Path, target: Path):
    logging.info(f"Updating {target}")

    for item in source.iterdir():
        dst = target / item.name

        if item.is_dir():
            shutil.copytree(item, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dst)

    logging.info("Files copied.")


def launch_program(target: Path):
    exe = target

    if exe.exists():
        logging.info(f"Launching {exe.name}")
        subprocess.Popen([str(exe)])
    else:
        logging.info("Executable not found.")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", required=False, help="Extracted update folder", default="C:/xenia-game-manager-portable/xenia-game-manager-portable.zip")
    parser.add_argument("--target", required=False, help="Installation folder", default="C:/xenia-game-manager-portable/")
    parser.add_argument("--source", required=False, help="Source folder", default="C:/xenia-game-manager-portable/")
    parser.add_argument("--exe", required=False, help="Executable", default="Xenia Game Manager.exe")
    parser.add_argument("--version", required=False, help="Version", default="0.0.0")
    parser.add_argument("--pid", type=int, required=False, help="PID of running app", default=6992)

    args = parser.parse_args()

    import logging
    import sys
    log_dir = get_app_dir() / "logs"
    log_dir.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_dir / "xenia_manager.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),  # Console output
        ],
    )

    zip_file = Path(args.zip)
    target = Path(args.target)
    exe = Path(args.exe)
    source = Path(args.source)
    pid = args.pid
    version = args.version

    config = load_config()
    default_exe = Path(config["xenia_game_manager_portable_path"]) / "Xenia Game Manager.exe"
    if not exe.exists(): exe = default_exe
    if pid != 1: wait_for_process(pid)

    if zip_file.exists():
        message = f"Extracting {zip_file}..."
        logging.info(message)
        if extract_archives(zip_file.parent, remove_archives=True) != 1:
            return False
        config["game_manager_version"] = version
        save_config(config)
    try:
        if source != target: copy_files(source, target)
        if exe.exists():
            time.sleep(5)
            launch_program(exe)
        logging.info("Update complete.")
        sys.exit(1)
    except Exception as e:
        logging.info(f"Update failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()