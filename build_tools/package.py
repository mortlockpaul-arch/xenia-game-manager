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

def copy_optimized_settings():
    settings_dest = ROOT / "src" / "assets" / "settings"
    settings_source_dir = Path(r"C:\Users\mortl\Documents\PycharmProjects\optimized-settings\settings")
    if settings_dest.exists():
        shutil.rmtree(settings_dest)
    for file in settings_source_dir.rglob("*"):
        if file.is_file():
            dest = settings_dest / file.relative_to(settings_source_dir)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file, dest)
            print("Copied:", dest)

if __name__ == "__main__":
    zip_portable()
    print(generate_guid())
    copy_optimized_settings()