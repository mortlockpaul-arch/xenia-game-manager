import shutil

from config import load_config, load_xenia_manager_config


def use_xenia_manager_content_folder_for_edge(log_callback=None):
    config = load_config()
    manager_config, xenia_manager_path = load_xenia_manager_config()
    if manager_config == {}:
        raise RuntimeError("Configure Xenia Manager No Configuration Exists")
        return
    unified_content: bool = (manager_config["emulators"]["settings"]["unified_content"])
    if not unified_content:
        raise RuntimeError(
            "XeniaManager Unified content is not enabled. ")

    manager_content = Path(config["xenia_manager_path"]) / "content"
    manager_content.mkdir(parents=True, exist_ok=True)
    manager_target = manager_content.resolve()

    edge_path = Path(config["xenia_edge_path"])
    edge_content = Path.home() / "Documents" / "Xenia" / "content"

    if (edge_path / "portable.txt").exists():
        edge_content = edge_path / "content"

    content_paths = {
        "Xenia Edge": edge_content,
        "Xenia Canary": Path(config["xenia_canary_path"]) / "content",
        "Xenia Netplay": Path(config["xenia_netplay_path"]) / "content",
        "Xenia Mouse Hook": Path(config["xenia_mousehook_path"]) / "content",
    }

    log = log_callback or print

    log(f"Using unified content folder: {manager_target}")

    for emulator, path in content_paths.items():

        if path.is_symlink():
            target = path.resolve()

            if target != manager_target:
                log(f"{emulator}: Incorrect content link detected.")
                log(f"  Current: {target}")
                log(f"  Expected: {manager_target}")

                path.unlink()
                path.symlink_to(manager_content, target_is_directory=True)

                log(f"{emulator}: Content link updated.")
            else:
                log(f"{emulator}: Already using the unified content folder.")

            continue

        if path.exists():
            log(f"{emulator}: Migrating existing content...")

            moved = 0

            for item in path.iterdir():
                destination = manager_content / item.name

                if not destination.exists():
                    shutil.move(str(item), str(destination))
                    moved += 1

            path.unlink()
            path.symlink_to(manager_content, target_is_directory=True)

            log(
                f"{emulator}: Migrated {moved} item(s) and linked to the unified content folder."
            )

        else:
            log(f"{emulator}: Creating content link.")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.symlink_to(manager_content, target_is_directory=True)

    log("All configured Xenia variants now use the unified Xenia Manager content folder.")

from pathlib import Path
import tomllib


def import_edge_games(log_callback=None):
    config = load_config()
    edge_path = Path(config["xenia_edge_path"])
    edge_library = Path.home() / "Documents" / "Xenia" / "library"

    if (edge_path / "portable.txt").exists():
        edge_library = edge_path / "library"

    games = []

    for toml_file in edge_library.glob("*/game.toml"):
        with toml_file.open("rb") as f:
            data = tomllib.load(f)

        for path_info in data.get("paths", []):
            label = path_info.get("label")

            game = {
                "title_id": data["title_id"],
                "name": f"{data['name']} ({label})" if label else data["name"],
                "path": path_info["path"],
                "default": path_info.get("default", False),
            }

            games.append(game)
            (log_callback or print)(game["name"])

    return games


if __name__ == "__main__":
    use_xenia_manager_content_folder_for_edge()
