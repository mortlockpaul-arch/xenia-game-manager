from pathlib import Path
import tomllib
from sys import exception

from config import load_config, load_xenia_manager_config

import shutil
from pathlib import Path


def use_xenia_manager_content_folder_for_edge():
    config = load_config()
    xenia_manager_path = Path(config["xenia_manager_path"])
    xenia_manager_config = load_xenia_manager_config(xenia_manager_path)
    unified_content: bool = (xenia_manager_config["emulators"]["settings"]["unified_content"])
    if not unified_content:
        raise RuntimeError(
            "XeniaManager Unified content is not enabled. ")

    manager_content = Path(config["xenia_manager_path"]) / "content"
    edge_content = Path.home() / "Documents" / "Xenia" / "content"

    manager_content.mkdir(parents=True, exist_ok=True)

    if edge_content.exists() and not edge_content.is_symlink():
        for item in edge_content.iterdir():
            destination = manager_content / item.name
            if not destination.exists():
                shutil.move(str(item), str(destination))

        edge_content.rmdir()

    if not edge_content.exists():
        edge_content.symlink_to(manager_content, target_is_directory=True)


def import_edge_games():
    library = Path(r"C:\Users\mortl\Documents\Xenia\library")
    games = []
    for toml_file in library.glob("*/game.toml"):
        with toml_file.open("rb") as f:
            data = tomllib.load(f)

        games.append({
            "title_id": data["title_id"],
            "name": data["name"],
            "paths": [p["path"] for p in data.get("paths", [])],
            "default_path": next(
                (p["path"] for p in data.get("paths", []) if p.get("default")),
                None,
            ),
        })

    for game in games:
        print(game)
    return games


if __name__ == "__main__":
    use_xenia_manager_content_folder_for_edge()
