import shutil
import os
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def zip_portable():
    build_dir = ROOT / "build" / "exe.win-amd64-3.14"
    out_zip = ROOT / "dist" / "XeniaGameManager-portable.zip"

    out_zip.parent.mkdir(exist_ok=True)

    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zipf:
        for file in build_dir.rglob("*"):
            zipf.write(file, file.relative_to(build_dir))

    print("Portable ZIP created:", out_zip)

if __name__ == "__main__":
    zip_portable()