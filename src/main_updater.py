import argparse
import logging
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


def wait_for_process(pid: int, timeout: int = 30):
    """Wait for the main application to exit."""
    print(f"Waiting for process {pid}...")

    try:
        import psutil

        while timeout > 0:
            if not psutil.pid_exists(pid):
                return
            time.sleep(1)
            timeout -= 1
    except ImportError:
        # Fallback if psutil isn't installed
        time.sleep(5)


def copy_files(source: Path, target: Path):
    print(f"Updating {target}")

    for item in source.iterdir():
        dst = target / item.name

        if item.is_dir():
            shutil.copytree(item, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dst)

    print("Files copied.")


def launch_program(target: Path):
    exe = target / "Xenia Game Manager.exe"

    if exe.exists():
        print(f"Launching {exe.name}")
        subprocess.Popen([str(exe)])
    else:
        print("Executable not found.")


    def log(message: str = "", console_log: bool=True, log_log:bool=True, clear_console:bool=False):
        timestamp = datetime.now().strftime("%H:%M:%S")
        if log_log: logging.info(message)
        return

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", required=True, help="Extracted update folder")
    parser.add_argument("--target", required=True, help="Installation folder")
    parser.add_argument("--pid", type=int, required=True, help="PID of running app")

    args = parser.parse_args()

    source = Path(args.zip)
    target = Path(args.target)

    wait_for_process(args.pid)

    try:
        copy_files(source, target)
        launch_program(target)
        print("Update complete.")
    except Exception as e:
        print(f"Update failed: {e}")
        input("Press Enter to exit...")
        sys.exit(1)


if __name__ == "__main__":
    main()