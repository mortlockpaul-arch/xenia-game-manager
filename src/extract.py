from pathlib import Path
import subprocess

from config import get_app_dir


def extract_archives(folder, log_callback=None, subfolder=False):
    """
    Extract .zip, .7z, .rar archives into subfolders named after the archive.
    Deletes archive only if extraction succeeds.
    """
    folder = Path(folder)
    count = 0
    root = get_app_dir()
    seven_zip_path = Path(get_app_dir()) / "assets" / "zip" / "7z.exe"
    for archive in folder.iterdir():
        if archive.suffix.lower() not in {".zip", ".7z", ".rar"}:
            continue

        if subfolder: output_dir = folder / archive.stem
        else: output_dir = folder

        if output_dir.exists():
            msg = f"Warning {output_dir.name} (folder already exists)"
            (log_callback or print)(msg)

        output_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            seven_zip_path,
            "x",                      # extract with full paths
            str(archive),
            f"-o{output_dir}",
            "-y",                     # assume yes
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                archive.unlink()
                count += 1
                msg = f"Extracted: {archive.name}"
                (log_callback or print)(msg)
            else:
                msg = f"Failed: {archive.name}\n{result.stderr}"
                (log_callback or print)(msg)

        except Exception as e:
            msg = f"Error: {archive.name} ({e})"
            (log_callback or print)(msg)

    if count == 0: (log_callback or print)(f"No archives found in {folder}")
    return count

if __name__ == "__main__":
    extract_archives(folder=r"C:\Users\mortl\Downloads", log_callback=print)