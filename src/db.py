# db.py

import sqlite3
import json
from pathlib import Path

from PySide6.QtWidgets import QMessageBox
from cx_Freeze import exception

import edge_import
from config import load_config, load_xenia_manager_config
from utils import detect_disc_number

DB_PATH = "db/games.db"

class Database:

    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()

    def import_multidisc_json(self, json_path, log_callback=None):
        """
        Import preservation metadata JSON
        """

        json_path = Path(json_path)

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        entries = data["entries"]

        with self.conn as con:

            for game in entries:

                title_id = game["title_id"]

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
                    title_id
                ))

                con.execute("""
                DELETE FROM discs
                WHERE title_id = ?
                """, (title_id,))

                for idx, label in enumerate(
                        game["disc_layout"],
                        start=1
                ):
                    con.execute("""
                    INSERT INTO discs
                    (
                        title_id,
                        disc_index,
                        label
                    )
                    VALUES (?, ?, ?)
                    """, (
                        title_id,
                        idx,
                        label
                    ))

        message = (
            f"Imported multi-disc metadata "
            f"for {len(entries)} games"
        )
        if log_callback:
            log_callback(message)

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
                favourite INTEGER DEFAULT 0,
                last_played TEXT,
                play_count INTEGER DEFAULT 0,
                play_time INTEGER DEFAULT 0,
                disc_count INTEGER DEFAULT 1,
                disc_type TEXT,
                xenia_disc_swap_required INTEGER DEFAULT 0,
                disc_number INTEGER DEFAULT 0,
                xenia_version TEXT
            )
            """)

            con.execute("""
            CREATE TABLE IF NOT EXISTS discs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title_id TEXT NOT NULL,
                disc_index INTEGER,
                label TEXT,
                FOREIGN KEY(title_id) REFERENCES games(game_id)
            )
            """)

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


    def import_games_from_edge_or_xeni_manager(self, json_path, games, log_callback=None):
        """
        Import Xenia Manager games.json
        """
        from edge_import import import_edge_games
        config = load_config()
        xenia_manager_installed = config["xenia_manager_installed"]
        if xenia_manager_installed:
            games_json = Path("config") / "games.json"
            xenia_manager_path = config["xenia_manager_path"]
            games_json_path = Path(xenia_manager_path) / games_json
            if not games_json_path.exists():
                raise Exception("Missing File")
            json_path = Path(json_path)

            if not json_path.exists():
                raise FileNotFoundError(json_path)

            with open(json_path, "r", encoding="utf-8") as f:
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
                    con.execute("""
                    INSERT INTO games
                    (
                        game_id,
                        media_id,
                        title,
                        file_path,
                        config_path,
                        play_time,
                        disc_number
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        game_id,
                        media_id,
                        title,
                        file_path,
                        config_path,
                        play_time,
                        detect_disc_number(file_path),
                    ))
                    self.import_multidisc_json(
                        r"config/multidisc.json", log_callback=log_callback
                    )
                    message = f"Imported {len(xenia_manager_games)} games"
                    log_callback(message)
                    return
        else:
            xenia_edge_installed = config["xenia_edge_installed"]
            xenia_edge_path = config["xenia_edge_path"]
            if xenia_edge_installed:
                xenia_edge_path = Path(xenia_edge_path)
                xenia_edge_games = import_edge_games()

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

                        file_path = game.get("default_path")  # or paths[0]
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
                            disc_number
                        )
                        VALUES (?, ?, ?, ?, ?)
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
