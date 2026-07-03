import shutil
import uuid
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def generate_guid():
    return str(uuid.uuid4())

def zip_portable():
    build_dir = ROOT / "build" / "exe.win-amd64-3.14"
    out_zip = ROOT / "dist" / "XeniaGameManager-portable.zip"

    out_zip.parent.mkdir(exist_ok=True)

    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zipf:
        for file in build_dir.rglob("*"):
            zipf.write(file, file.relative_to(build_dir))

    print("Portable ZIP created:", out_zip)
from pathlib import Path
import shutil
import filecmp
from pathlib import Path
import shutil
import filecmp

def copy_optimized_settings():
    settings_dest = ROOT / "src" / "assets" / "settings"
    settings_source_dir = Path(r"C:\Users\mortl\Documents\PycharmProjects\optimized-settings\settings")

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
            print(f"Copied: {dst}")

    if copied == 0:
        print("All optimized settings are already up to date.")
    else:
        print(f"Updated {copied} file(s).")

if __name__ == "__main__":
    zip_portable()
    print(generate_guid())
    copy_optimized_settings()