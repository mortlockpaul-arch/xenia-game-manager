import filecmp
import shutil
import subprocess
import sys
import uuid
import zipfile
from pathlib import Path

from config import load_config, save_config

root = Path(__file__).parent
print (root)

def generate_guid():
    return str(uuid.uuid4())

def zip_portable():
    build_dir = Path(root / "build") / "exe.win-amd64-3.14"
    out_zip = Path(root / "dist") / "xenia-game-manager-portable.zip"
    # Remove the dist folder if it exists
    if out_zip.parent.exists():
        shutil.rmtree(out_zip.parent)
        print("Deleting existing folder:", out_zip.parent)
    out_zip.parent.mkdir(exist_ok=True)

    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zipf:
        for file in build_dir.rglob("*"):
            if file.name == "portable.txt":
                continue
            zipf.write(file, file.relative_to(build_dir))
            # Add portable.txt to the root of the ZIP
        if not (build_dir / "portable.txt").exists():
            zipf.writestr("portable.txt", "")
    print("portable zip created: ", out_zip)

def create_defaults(version):
    print("Creating default game manager database and configuration files...")

    base_path = root.parent / "src"
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

    config = load_config(default_path)
    config["game_manager_version"] = version
    save_config(config, default_path)

    backup_existing(config_target)

    if default_config.exists():
        print(f"  Installing default configuration: {config_target}")
        shutil.copy2(default_config, config_target)
    else:
        print(f"  Default configuration not found: {default_config}")

    print("Done.")

def copy_optimized_settings():
    settings_dest = root / "src" / "assets" / "settings"
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

def copy_updater():
    settings_dest = root / "build_tools/build/exe.win-amd64-3.14"
    settings_source_dir = Path(r"C:\Users\mortl\PycharmProjects\xenia-game-manager-updater\build\exe.win-amd64-3.14")

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
        print("Updater is already up to date.")
    else:
        print(f"Updated {copied} file(s).")

create_defaults(version="0.9.9")
copy_optimized_settings()

# Build the executable
subprocess.run([sys.executable, "setup.py", "build_exe"], check=True)

zip_portable()

# Build the MSI
subprocess.run([sys.executable, "setup.py", "bdist_msi"], check=True)