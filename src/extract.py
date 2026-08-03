import subprocess
from pathlib import Path

from config import get_app_dir

from PySide6.QtCore import QObject, Signal, Slot

from pathlib import Path

class ExtractWorker(QObject):
    finished = Signal(int)
    log_window = Signal(str)

    def __init__(self, folders: list[Path]):
        super().__init__()
        self.folders: list[Path] = folders

    @Slot()
    def run(self):
        total = 0

        try:
            for folder in self.folders:
                total += extract_archives(
                    folder=folder,
                    log_callback=self.log_window.emit,
                    remove_archives=True,
                )
        finally:
            self.finished.emit(total)


def extract_archives(folder, log_callback=None, subfolder=False, remove_archives=True):

    def log(msg):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    folder = Path(folder)

    log(f"Folder: {folder.name}")

    count = 0
    seven_zip_path = Path(get_app_dir()) / "assets" / "zip" / "7z.exe"

    for archive in folder.iterdir():

        if archive.suffix.lower() not in {".zip", ".7z", ".rar"}:
            continue

        output_dir = folder / archive.stem if subfolder else folder

        root = get_app_dir() / "downloads"
        relative_path = Path(archive).relative_to(folder)
        log(f"Archive: {relative_path}")

        output_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            str(seven_zip_path),
            "x",
            str(archive),
            f"-o{output_dir}",
            "-y",
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True
            )

            if result.returncode == 0:

                if remove_archives:
                    archive.unlink()

                count += 1
                log(f"Extracted: {relative_path}")

            else:
                log(f"Failed: {relative_path}\n{result.stderr}")

        except Exception as e:
            log(f"Error: {relative_path} ({e})")

    if count == 0:
        log(f"No archives found in {folder}")

    return count

if __name__ == "__main__":
    extract_archives(folder=r"C:\Users\mortl\Downloads", log_callback=print)