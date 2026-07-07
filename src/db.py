# db.py

import sqlite3
import json
from pathlib import Path

import requests
from PySide6.QtWidgets import QMessageBox
from cx_Freeze import exception

import edge_import
from config import load_config, load_xenia_manager_config
from utils import detect_disc_number

DB_PATH = "db/games.db"


class Compatibility:

    def __init__(self, db):
        self.compatibility = None
        self.db = db

    def download_compatibility(self):
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "XeniaGameManager"
        }
        config = load_config()
        api = config["xenia_game_compatibility_url"]
        release = requests.get(api, headers=headers, timeout=30)
        release.raise_for_status()

        release = release.json()

        print(release["tag_name"])

        for asset in release["assets"]:
            print(asset["name"], asset["browser_download_url"])

        asset = next(
            a for a in release["assets"]
            if a["name"].endswith(".json")
        )

        download_url = asset["browser_download_url"]

        response = requests.get(download_url, headers=headers, timeout=60)
        response.raise_for_status()

        self.compatibility = response.json()

        with open("compatibility.json", "wb") as f:
            f.write(response.content)

    def update_compatibility(self):
        if self.compatibility is None:
            with open("compatibility.json", "r", encoding="utf-8") as f:
                self.compatibility = json.load(f)

        compat_by_title: dict[str, dict[str, Any]] = {
            game["id"]: game
            for game in self.compatibility
        }

        con = self.db.get_db()
        rows = con.execute(
            "SELECT game_id FROM games"
        ).fetchall()

        for row in rows:
            compat = compat_by_title.get(row["game_id"].upper())
            if compat is not None:
                print(compat["state"])
            if compat:
                con.execute(
                    """
                    UPDATE games
                    SET compatibility_rating = ?,
                        compatibility_issue = ?,
                        compatibility_updated = CURRENT_TIMESTAMP
                    WHERE game_id = ?
                    """,
                    (
                        compat["state"],
                        compat.get("issue", ""),
                        row["game_id"],
                    ),
                )

        con.commit()

class Database:

    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()

    def import_multidisc_json(self, json_path, log_callback=None):
        """Import preservation metadata JSON."""

        with open(json_path, "r", encoding="utf-8") as f:
            entries = json.load(f)["entries"]

        imported = 0

        with self.conn as con:
            for game in entries:
                title_id = game["title_id"]

                # Skip games that aren't in the library
                if not con.execute(
                        "SELECT 1 FROM games WHERE game_id = ?",
                        (title_id,)
                ).fetchone():
                    continue

                imported += 1

                con.execute("""
                    UPDATE games
                    SET
                        disc_count = ?,
                        disc_type = ?,
                        xenia_disc_swap_required = ?
                    WHERE game_id = ?
                """, (
                    game["disc_count"],
                    game["disc_type"],
                    int(game["xenia_disc_swap_required"]),
                    title_id,
                ))

                con.execute(
                    "DELETE FROM discs WHERE title_id = ?",
                    (title_id,)
                )

                con.executemany("""
                    INSERT INTO discs (
                        title_id,
                        disc_index,
                        label
                    )
                    VALUES (?, ?, ?)
                """, [
                    (title_id, index, label)
                    for index, label in enumerate(game["disc_layout"], start=1)
                ])

        if log_callback:
            log_callback(
                f"Imported multi-disc metadata for {imported} games"
            )

    def get_game_discs(self, title_id):

        with self.conn as con:
            return [
                dict(row)
                for row in con.execute("""
                    SELECT
                        disc_index,
                        label,
                        file_path
                    FROM discs
                    WHERE title_id = ?
                    ORDER BY disc_index
                """, (title_id,))
            ]
    def get_multidisc_games(self):

        with self.conn as con:
            return [
                dict(row)
                for row in con.execute("""
                    SELECT
                        game_id,
                        title,
                        disc_count,
                        disc_type
                    FROM games
                    WHERE disc_count > 1
                    ORDER BY title
                """)
            ]

    def get_db(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
        return self.conn


    def clear_db(self):
        with self.conn as con:
            con.execute("DELETE FROM discs")
            con.execute("DELETE FROM games")
            con.execute("DELETE FROM favourites")
            con.execute(
                "DELETE FROM sqlite_sequence WHERE name='discs'"
            )
            con.execute(
                "DELETE FROM sqlite_sequence WHERE name='games'"
            )
            con.commit()


    def init_db(self):
        with self.conn as con:
            con.execute("""
            CREATE TABLE IF NOT EXISTS games (
                game_no INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id TEXT,
                media_id TEXT,
                title TEXT NOT NULL,
                file_path TEXT,
                config_path TEXT,
                last_played TEXT,
                play_count INTEGER DEFAULT 0,
                play_time INTEGER DEFAULT 0,
                disc_count INTEGER DEFAULT 1,
                disc_type TEXT,
                xenia_disc_swap_required INTEGER DEFAULT 0,
                disc_number INTEGER DEFAULT 0,
                xenia_version TEXT,
                compatibility_rating TEXT,
                compatibility_issue TEXT,
                compatibility_updated CURRENT_TIMESTAMP
            )
            """)

            con.execute("""
            CREATE TABLE IF NOT EXISTS favourites (
                game_id TEXT PRIMARY KEY ,
                favourite INTEGER DEFAULT 0
            )
            """)

            con.execute("""
            CREATE TABLE IF NOT EXISTS discs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title_id TEXT NOT NULL,
                disc_index INTEGER,
                label TEXT
            )
            """)

            con.execute("""
            CREATE VIEW IF NOT EXISTS disc_view AS
                SELECT
                    d.id,
                    d.title_id,
                    g.title,
                    d.disc_index,
                    d.label
                FROM discs d
                JOIN games g
                    ON d.title_id = g.game_id;""")

            con.execute("""
            CREATE INDEX IF NOT EXISTS idx_games_title
            ON games(title)
            """)

            con.execute("""
            CREATE INDEX IF NOT EXISTS idx_discs_title_id
            ON discs(title_id)
            """)


    def export_titles_to_xenia_manager_game_list(self):
        import json
        config = load_config()
        xenia_manager_installed = config["xenia_manager_installed"]
        if xenia_manager_installed:
            xenia_manager_path = Path(config["xenia_manager_path"])
            xenia_manager_config = load_xenia_manager_config(xenia_manager_path)
            games_json = Path("config") / "games.json"
            xenia_manager_path = config["xenia_manager_path"]
            games_json_path = Path(xenia_manager_path) / games_json
            if not games_json_path.exists():
                raise Exception("Missing File")
            with open(games_json_path, "r", encoding="utf-8") as f:
                games = json.load(f)

            with self.conn as con:

                db_titles = {
                    row["game_id"]: row["title"]
                    for row in con.execute(
                        """
                        SELECT game_id, title
                        FROM games
                        """
                    ).fetchall()
                }

            updated = 0

            for game in games:

                game_id = game.get("game_id")

                if game_id in db_titles:

                    new_title = db_titles[game_id]

                    if game.get("title") != new_title:
                        game["title"] = new_title
                        updated += 1

            with open(games_json_path, "w", encoding="utf-8") as f:
                json.dump(
                    games,
                    f,
                    indent=2,
                    ensure_ascii=False
                )

            return updated
        else:
            raise Exception("Xenia Manager Not Installed")


    def import_games_from_edge_or_xenia_manager(self, xenia_version, games, log_callback=None):
        print(xenia_version)
        from edge_import import import_edge_games
        config = load_config()
        xenia_manager_installed = config["xenia_manager_installed"]
        xenia_edge_installed = config["xenia_edge_installed"]
        if xenia_version == "xenia_manager":
            if not  xenia_manager_installed:
                raise Exception("Xenia Manager Not Installed")
            games_json = Path("config") / "games.json"
            xenia_manager_path = config["xenia_manager_path"]
            games_json_path = Path(xenia_manager_path) / games_json
            if not games_json_path.exists():
                raise Exception("Missing File")

            if not games_json_path.exists():
                raise FileNotFoundError(games_json_path)

            with open(games_json_path, "r", encoding="utf-8") as f:
                xenia_manager_games = json.load(f)

            if len(xenia_manager_games) == len(games):
                message = f"Import Not Required {len(xenia_manager_games)} games"
                if log_callback:
                    log_callback(message)
                    return

            self.clear_db()

            with self.conn as con:

                for game in xenia_manager_games:
                    game_id = game.get("game_id")
                    title = game.get("title")
                    media_id = game.get("media_id")

                    file_path = (
                        game.get("file_locations", {})
                        .get("game")
                    )
                    config_path = (
                        game.get("file_locations", {})
                        .get("config")
                    )
                    play_time = (game.get("playtime"))
                    xenia_version = game.get("xenia_version")
                    disc_number = detect_disc_number(file_path)
                    con.execute("""
                    INSERT INTO games
                    (
                        game_id,
                        media_id,
                        title,
                        file_path,
                        config_path,
                        play_time,
                        disc_number,
                        xenia_version
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        game_id,
                        media_id,
                        title,
                        file_path,
                        config_path,
                        play_time,
                        disc_number,
                        xenia_version
                    ))
                self.import_multidisc_json(
                    r"config/multidisc.json", log_callback=log_callback
                )
                message = f"Imported {len(xenia_manager_games)} games"
                log_callback(message)
                compatibility = Compatibility(self)
                compatibility.update_compatibility()
                return
        else:
            if xenia_version == "xenia_edge":
                if not xenia_edge_installed:
                    raise Exception("Xenia Edge Not Installed")
            xenia_edge_path = config["xenia_edge_path"]
            xenia_edge_games = import_edge_games(log_callback=log_callback)

            if len(xenia_edge_games) == len(games):
                message = f"Import Not Required {len(xenia_edge_games)} games"
                if log_callback:
                    log_callback(message)
                    return

            self.clear_db()

            with self.conn as con:

                for game in xenia_edge_games:
                    game_id = game.get("title_id")
                    title = game.get("name")
                    settings = Path(r"C:\Users\mortl\Documents\Xenia\config")

                    file_path = game.get("path")  # or paths[0]
                    config_path = str(settings / f"{game_id}.config.toml")
                    print(game_id)
                    print(title)
                    print(file_path)
                    print(config_path)
                    con.execute("""
                    INSERT INTO games
                    (
                        game_id,
                        title,
                        file_path,
                        config_path,
                        disc_number,
                        xenia_version
                    )
                    VALUES (?, ?, ?, ?, ?, "Edge")
                    """, (
                        game_id,
                        title,
                        file_path,
                        config_path,
                        detect_disc_number(file_path),
                    ))
            self.import_multidisc_json(
                    r"config/multidisc.json", log_callback=log_callback
                )
            message = f"Imported {len(xenia_edge_games)} games"
            log_callback(message)
            compatibility = Compatibility(self)
            compatibility.update_compatibility()
            return


    def search_games(self, search_text=""):
        with self.conn as con:

            query = """
            SELECT *
            FROM games
            """

            params = ()

            if search_text:
                query += " WHERE title LIKE ?"
                params = (f"%{search_text}%",)

            query += " ORDER BY title"

            return [dict(row) for row in con.execute(query, params)]


    def get_discs(self, title_id):
        with self.conn as con:
            return con.execute("""
            SELECT *
            FROM discs
            WHERE title_id = ?
            ORDER BY disc_index
            """, (
                title_id,
            )).fetchall()


if __name__ == "__main__":
    db = Database()
    db.init_db()

    # Example:
    #
    # import_games_json(
    #     r"D:\RetroBat\emulators\xenia-manager\Config\games.json"
    # )
    #
    # import_multidisc_json(
    #     r"multidisc.json"
    # )

    print("Database initialized")
