# db.py
import shutil
import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import requests
from PySide6.QtWidgets import QMessageBox
from cx_Freeze import exception

import edge_import
from config import load_config, load_xenia_manager_config, get_app_dir
from utils import detect_disc_number, strip_disc_suffix

DB_PATH = "db/games.db"


class Compatibility:

    def __init__(self, db, log_call_back=None):
        self.compatibility = None
        root = get_app_dir()
        self.compatibility_file = root / "config" / "compatibility.json"
        if self.compatibility_file.exists():
            modified = datetime.fromtimestamp(self.compatibility_file.stat().st_mtime)

            if datetime.now() - modified >= timedelta(days=1):
                (log_call_back or print)(f"File {self.compatibility_file} is 1 day old or older. Downloading compatibility data.")
                self.download_compatibility()
            else:
                (log_call_back or print)(f"File {self.compatibility_file} is not 1 day old or older. Not downloading compatibility data.")
        else:
            (log_call_back or print)(f"File {self.compatibility_file} does not exist. Downloading compatibility data.")
            self.download_compatibility()

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

        with open(self.compatibility_file, "wb") as f:
            f.write(response.content)

    def update_compatibility(self):
        if self.compatibility is None:
            with open(self.compatibility_file, "r", encoding="utf-8") as f:
                self.compatibility = json.load(f)

        compat_by_title: dict[str, dict[str, Any]] = {
            game["id"].upper(): game
            for game in self.compatibility
        }

        with self.db.get_db() as con:
            rows = con.execute(
                "SELECT game_id FROM games"
            ).fetchall()

            for row in rows:
                game_id = row["game_id"].upper()
                compat = compat_by_title.get(game_id)

                if compat:
                    print(compat["state"])

                    con.execute("""
                        INSERT INTO compatibility (
                            game_id,
                            compatibility_rating,
                            compatibility_issue,
                            compatibility_updated
                        )
                        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                        ON CONFLICT(game_id)
                        DO UPDATE SET
                            compatibility_rating = excluded.compatibility_rating,
                            compatibility_issue = excluded.compatibility_issue,
                            compatibility_updated = CURRENT_TIMESTAMP
                    """, (
                        row["game_id"],
                        compat["state"],
                        compat.get("issue", ""),
                    ))

class Database:

    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
        self.conn.execute("PRAGMA foreign_keys = ON")

    def import_multidisc_json(self, json_path, log_callback=None):
        """Import preservation metadata JSON."""

        with open(json_path, "r", encoding="utf-8") as f:
            entries = json.load(f)["entries"]

        imported = 0

        with self.conn as con:
            for game in entries:
                game_id = game["title_id"]

                # Skip games that aren't in the library
                if not con.execute(
                        "SELECT 1 FROM games WHERE game_id = ?",
                        (game_id,)
                ).fetchone():
                    continue

                imported += 1

                con.execute("""
                    UPDATE games
                    SET title = ?
                    WHERE game_id = ?
                """, (
                    game["title"],
                    game_id,
                ))

                for index, label in enumerate(game["disc_layout"], start=1):
                    con.execute("""
                        INSERT INTO discs (
                            game_id,
                            disc_count,
                            disc_type,
                            disc_swap_required,
                            disc_number,
                            label
                        )
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(game_id, disc_number)
                        DO UPDATE SET
                            disc_count = excluded.disc_count,
                            disc_type = excluded.disc_type,
                            disc_swap_required = excluded.disc_swap_required,
                            label = excluded.label
                    """, (
                        game_id,
                        game["disc_count"],
                        game["disc_type"],
                        int(game["xenia_disc_swap_required"]),
                        index,
                        label
                    ))

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
                        disc_number,
                        label,
                        file_path
                    FROM discs
                    WHERE title_id = ?
                    ORDER BY disc_number
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

    from contextlib import contextmanager
    import sqlite3

    @contextmanager
    def get_db(self):
        con = sqlite3.connect(DB_PATH)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")

        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def clear_db(self, delete_favourites=False, delete_discs=False):
        with self.conn as con:
            if delete_discs:
                con.execute("DELETE FROM discs")
                con.execute("DELETE FROM sqlite_sequence WHERE name='discs'")
            con.execute("DELETE FROM games")
            if delete_favourites: con.execute("DELETE FROM favourites")
            con.execute("DELETE FROM sqlite_sequence WHERE name='games'")
            con.commit()

    def init_db(self):
        with self.conn as con:
            con.execute("""
            CREATE TABLE IF NOT EXISTS games (
                game_id TEXT NOT NULL PRIMARY KEY,
                title TEXT NOT NULL,
                config_path TEXT,
                xenia_version TEXT,
                UNIQUE(game_id)
            );
            """)
            con.execute("""
            CREATE TABLE IF NOT EXISTS compatibility (
                game_id TEXT PRIMARY KEY,
                compatibility_rating TEXT,
                compatibility_issue TEXT,
                compatibility_updated DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            """)

            con.execute("""
            CREATE TABLE IF NOT EXISTS gameplay (
                game_id TEXT PRIMARY KEY,
                last_played TEXT,
                play_count INTEGER DEFAULT 0,
                play_time INTEGER DEFAULT 0
            );
            """)

            con.execute("""
            CREATE TABLE IF NOT EXISTS favourites (
                game_id TEXT PRIMARY KEY,
                favourite INTEGER DEFAULT 0
            );
            """)

            con.execute("""
            CREATE TABLE IF NOT EXISTS discs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id TEXT NOT NULL,
                media_id TEXT,
                file_path TEXT,
                disc_count INTEGER DEFAULT 1,
                disc_type TEXT,
                disc_swap_required INTEGER DEFAULT 0,
                disc_number INTEGER DEFAULT 1,
                label TEXT,
                UNIQUE(game_id, disc_number),
            
                FOREIGN KEY (game_id)
                    REFERENCES games(game_id)
                    ON DELETE CASCADE
            );
            """)
            con.execute("""
            CREATE VIEW IF NOT EXISTS game_view AS
            SELECT
                g.game_id,
                d.media_id,
                CASE
                    WHEN d.disc_count > 1
                    THEN g.title || ' - ' || d.label
                    ELSE g.title
                END AS title,
                g.config_path,
                g.xenia_version,

                d.file_path,
                d.disc_number,
                d.disc_count,
                d.disc_type,
                d.disc_swap_required,
                d.label,

                COALESCE(f.favourite, 0) AS favourite,

                p.last_played,
                COALESCE(p.play_count, 0) AS play_count,
                COALESCE(p.play_time, 0) AS play_time,

                c.compatibility_rating,
                c.compatibility_issue,
                c.compatibility_updated

            FROM games g

            JOIN discs d
                ON g.game_id = d.game_id

            LEFT JOIN gameplay p
                ON g.game_id = p.game_id

            LEFT JOIN compatibility c
                ON g.game_id = c.game_id

            LEFT JOIN favourites f
                ON g.game_id = f.game_id;
            """)

            con.execute("""
            CREATE VIEW IF NOT EXISTS disc_view AS
            SELECT
                d.id,
                d.game_id,
                g.title,
                d.disc_number,
                d.file_path,
                d.label
            FROM discs d
            JOIN games g
                ON d.game_id = g.game_id;
            """)

            con.execute("""
            CREATE INDEX IF NOT EXISTS idx_games_title
            ON games(title)
            """)

            con.execute("""
            CREATE INDEX IF NOT EXISTS idx_discs_title_id
            ON discs(game_id)
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
        multidisc_info = get_app_dir() / "config" / "multidisc.json"

        if xenia_version == "xenia_manager":
            if not  xenia_manager_installed:
                raise Exception("Xenia Manager Not Installed")
            games_json = Path("config") / "games.json"
            xenia_manager_path = config["xenia_manager_path"]
            games_json_path = Path(xenia_manager_path) / games_json
            shutil.copy2(games_json_path, get_app_dir() / "config" / "games.json")
            log_callback(f"Copied {games_json_path} to {get_app_dir() / "config" / "games.json"} You can compare later to spot difference.")
            if not games_json_path.exists():
                raise FileNotFoundError(games_json_path)

            with open(games_json_path, "r", encoding="utf-8") as f:
                xenia_manager_games = json.load(f)

            if len(xenia_manager_games) == len(games):
                message = f"Import Not Required {len(xenia_manager_games)} games"
                if log_callback:
                    log_callback(message)
                    return

            # self.clear_db()
            message = f"Imported {len(xenia_manager_games)} Games from Xenia Manager"
            with self.conn as con:

                for game in xenia_manager_games:
                    game_id = game.get("game_id")
                    title = game.get("title")
                    media_id = game.get("media_id")
                    title = strip_disc_suffix(title)
                    file_path = (game.get("file_locations", {}).get("game"))
                    config_path = (game.get("file_locations", {}).get("config"))
                    play_time = (game.get("playtime"))
                    xenia_version = game.get("xenia_version")
                    disc_number = detect_disc_number(file_path)
                    disc_type = "XBLA" if game_id.lower() in file_path.lower() else "DVD"
                    con.execute("""
                        INSERT INTO games (
                            game_id,
                            title,
                            config_path,
                            xenia_version
                        )
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(game_id)
                        DO UPDATE SET
                            title = excluded.title,
                            config_path = excluded.config_path,
                            xenia_version = excluded.xenia_version
                    """, (
                        game_id,
                        title,
                        config_path,
                        xenia_version,
                    ))

                    con.execute("""
                        INSERT INTO gameplay (
                            game_id,
                            play_time
                        )
                        VALUES (?, ?)
                        ON CONFLICT(game_id)
                        DO UPDATE SET
                            play_time = excluded.play_time
                    """, (
                        game_id,
                        play_time,
                    ))
                    con.execute("""
                        INSERT INTO discs (
                            game_id,
                            media_id,
                            disc_number,
                            file_path,
                            disc_type
                        )
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(game_id, disc_number)
                        DO UPDATE SET
                            game_id = excluded.game_id,
                            disc_number = excluded.disc_number,
                            disc_type = excluded.disc_type
                    """, (
                        game_id,
                        media_id,
                        disc_number,
                        file_path,
                        disc_type,
                    ))


        else:
            if xenia_version == "xenia_edge":
                if not xenia_edge_installed:
                    raise Exception("Xenia Edge Not Installed")
            xenia_edge_path = config["xenia_edge_path"]
            xenia_edge_games = import_edge_games(log_callback=log_callback)
            xenia_version = "Edge"
            if len(xenia_edge_games) == len(games):
                message = f"Import Not Required {len(xenia_edge_games)} games"
                if log_callback:
                    log_callback(message)
                    return

            # self.clear_db()
            message = f"Imported {len(xenia_edge_games)} Games From Edge"
            with self.conn as con:
                old_media = {
                    (row["game_id"], row["disc_number"]): row["media_id"]
                    for row in con.execute("""
                        SELECT game_id, disc_number, media_id
                        FROM discs
                        WHERE media_id IS NOT NULL
                    """)
                }

                for game in xenia_edge_games:
                    game_id = game.get("title_id")
                    file_path = game.get("path")  # or paths[0]
                    disc_number = detect_disc_number(file_path)
                    old_id = old_media.get((game_id, disc_number))
                    media_id = None
                    if media_id is None:
                        media_id = old_id
                    title = game.get("name")
                    edge_path = Path(config["xenia_edge_path"])
                    edge_configs = Path.home() / "Documents" / "Xenia" / "config"

                    if (edge_path / "portable.txt").exists():
                        edge_configs = edge_path / "content"


                    config_path = str(edge_configs / f"{game_id}.config.toml")
                    disc_type = "XBLA" if game_id.lower() in file_path.lower() else "DVD"
                    print(game_id)
                    print(title)
                    print(file_path)
                    print(config_path)
                    con.execute("""
                        INSERT INTO games (
                            game_id,
                            title,
                            config_path,
                            xenia_version
                        )
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(game_id)
                        DO UPDATE SET
                            title = excluded.title,
                            config_path = excluded.config_path,
                            xenia_version = excluded.xenia_version
                    """, (
                        game_id,
                        title,
                        config_path,
                        xenia_version,
                    ))
                    con.execute("""
                        INSERT INTO discs (
                            game_id,
                            media_id,
                            disc_number,
                            file_path,
                            disc_type
                        )
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(game_id, disc_number)
                        DO UPDATE SET
                            game_id = excluded.game_id,
                            disc_number = excluded.disc_number,
                            disc_type = excluded.disc_type
                    """, (
                        game_id,
                        media_id,
                        disc_number,
                        file_path,
                        disc_type,
                    ))

        compatibility = Compatibility(self)
        compatibility.update_compatibility()

        self.import_multidisc_json(multidisc_info, log_callback=log_callback)
        log_callback(message)

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
            ORDER BY disc_number
            """, (
                title_id,
            )).fetchall()


if __name__ == "__main__":
    # db = Database()
    # db.init_db()

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
