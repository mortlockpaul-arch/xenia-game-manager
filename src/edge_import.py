from pathlib import Path
import tomllib

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
