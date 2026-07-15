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

from pathlib import Path

def zip_portable():
    build_dir = Path("build") / "exe.win-amd64-3.14"
    out_zip = Path("dist") / "xenia-game-manager-portable.zip"
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

import shutil
from pathlib import Path

import shutil
from pathlib import Path

def create_defaults():
    print("Creating default game manager database and configuration files...")

    base_path = Path.cwd().parent / "src"
    default_path = base_path / "assets" / "default"

    db_dir = base_path / "db"
    config_dir = base_path / "config"

    backup_dir = base_path / "backup"
    backup_dir.mkdir(parents=True, exist_ok=True)

    db_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)

    def backup_existing(path: Path):
        if not path.exists():
            print(f"  No existing file to back up: {path.name}")
            return

        backup = backup_dir / path.name

        if backup.exists():
            print(f"  Removing old backup: {backup.name}")
            backup.unlink()

        print(f"  Backing up {path.name} -> {backup}")
        shutil.move(path, backup)

    # Database
    default_db = default_path / "games.db"
    db_target = db_dir / "games.db"

    backup_existing(db_target)

    if default_db.exists():
        print(f"  Installing default database: {db_target}")
        shutil.copy2(default_db, db_target)
    else:
        print(f"  Default database not found: {default_db}")

    # Configuration
    default_config = default_path / "game-manager-config.json"
    config_target = config_dir / "game-manager-config.json"

    backup_existing(config_target)

    if default_config.exists():
        print(f"  Installing default configuration: {config_target}")
        shutil.copy2(default_config, config_target)
    else:
        print(f"  Default configuration not found: {default_config}")

    print("Done.")

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
    create_defaults()
    copy_optimized_settings()
    zip_portable()