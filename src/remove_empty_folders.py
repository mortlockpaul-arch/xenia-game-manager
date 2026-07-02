from pathlib import Path
from PySide6.QtWidgets import QFileDialog, QMessageBox

import os


def remove_empty_folders(root_folder, log_callback=None):
    total_removed = 0

    while True:
        removed_this_pass = 0

        for current_dir, dirs, files in os.walk(root_folder, topdown=False):
            try:
                if not dirs and not files:
                    os.rmdir(current_dir)
                    removed_this_pass += 1
                    total_removed += 1

                    if log_callback:
                        log_callback(f"Removed: {current_dir}")

            except OSError:
                pass

        if removed_this_pass == 0:
            break

    return total_removed