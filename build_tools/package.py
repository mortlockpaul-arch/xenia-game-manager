import filecmp
import shutil
import uuid
import zipfile
from pathlib import Path
import tempfile
import win32com.shell.shell as shell
import win32con

from ui import resource_path

ROOT = Path(__file__).resolve().parent.parent

def disk_fix():
    script = """
select volume G
delete volume

select volume H
extend
"""

    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt") as f:
        f.write(script)
        script_path = f.name
    rc = shell.ShellExecuteEx(
        lpVerb="runas",
        lpFile="diskpart.exe",
        lpParameters=f'/s "{script_path}"',
        nShow=win32con.SW_SHOWNORMAL,
    )
    if rc <= 32:
        raise RuntimeError("Failed to launch DiskPart or the UAC prompt was cancelled.")


def generate_guid():
    return str(uuid.uuid4())


def zip_portable():
    build_dir = ROOT / "build" / "exe.win-amd64-3.14"
    out_zip = ROOT / "dist" / "xenia-game-manager-portable.zip"

    out_zip.parent.mkdir(exist_ok=True)

    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zipf:
        for file in build_dir.rglob("*"):
            if file.name == "portable.txt":
                continue
            zipf.write(file, file.relative_to(build_dir))
            # Add portable.txt to the root of the ZIP
        if not (build_dir / "portable.txt").exists():
            zipf.writestr("portable.txt", "")
    print("Portable ZIP created:", out_zip)

def create_defaults():
    print("Creating default game manager")

    base_path = Path.cwd().parent / "src"
    default_path = base_path / "assets" / "default"

    db_dir = base_path / "db"
    config_dir = base_path / "config"

    db_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)

    def backup_existing(path):
        if path.exists():
            backup = path.with_name(path.name + ".previous")

            if backup.exists():
                backup.unlink()

            path.rename(backup)

    # Copy database
    default_db = default_path / "games.db"
    db_target = db_dir / "games.db"

    backup_existing(db_target)

    if default_db.exists():
        shutil.copy2(default_db, db_target)

    # Copy config
    default_config = default_path / ".x360-game-manager-config.json"
    config_target = config_dir / ".x360-game-manager-config.json"

    backup_existing(config_target)

    if default_config.exists():
        shutil.copy2(default_config, config_target)

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
    # print(generate_guid())
    copy_optimized_settings()
    create_defaults()
    # disk_fix()