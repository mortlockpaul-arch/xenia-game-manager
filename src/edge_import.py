from pathlib import Path
import tomllib
from sys import exception

from config import load_config, load_xenia_manager_config

import shutil
from pathlib import Path


def use_xenia_manager_content_folder_for_edge(log_callback=None):
    config = load_config()
    xenia_manager_path = Path(config["xenia_manager_path"])
    xenia_manager_config = load_xenia_manager_config(xenia_manager_path)
    unified_content: bool = (xenia_manager_config["emulators"]["settings"]["unified_content"])
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
        "edge_content": edge_content,
        "canary_content": Path(config["xenia_canary_path"]) / "content",
        "netplay_content": Path(config["xenia_netplay_path"]) / "content",
        "mouse_hook_content": Path(config["xenia_mousehook_path"]) / "content",
    }

    for name, path in content_paths.items():
        if path.is_symlink():
            if path.resolve() != manager_target:
                (log_callback or print)(f"{name}: Incorrect symlink ({path.readlink()})")
                path.unlink()
                path.symlink_to(manager_content, target_is_directory=True)
                (log_callback or print)(f"{name}: Fixed -> {manager_content}")
        if path.is_symlink():
            (log_callback or print)(f"{name} points to: {path.readlink()}")
            (log_callback or print)(f"{name} resolved to: {path.resolve()}")
            continue
        if path.exists() and not path.is_symlink():
            (log_callback or print)(f"Moving content and creating symlink for {name}")
            for item in path.iterdir():
                destination = manager_content / item.name
                if not destination.exists():
                    shutil.move(str(item), str(destination))
            path.unlink()
            path.symlink_to(manager_content, target_is_directory=True)
        if not path.exists():
            (log_callback or print)(f"{name}: Missing folder, creating symlink -> {manager_content}")

            path.parent.mkdir(parents=True, exist_ok=True)
            path.symlink_to(manager_content, target_is_directory=True)

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
