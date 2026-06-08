# db.py

import sqlite3
import json
from pathlib import Path

DB_PATH = "games.db"


def get_db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    with get_db() as con:

        con.execute("""
        CREATE TABLE IF NOT EXISTS games (
            game_id TEXT,
            title TEXT NOT NULL,
            file_path TEXT,
            favourite INTEGER DEFAULT 0,
            last_played TEXT,
            play_count INTEGER DEFAULT 0,
            disc_count INTEGER DEFAULT 1,
            disc_type TEXT,
            xenia_disc_swap_required INTEGER DEFAULT 0
        )
        """)

        con.execute("""
        CREATE TABLE IF NOT EXISTS discs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title_id TEXT NOT NULL,
            disc_index INTEGER,
            label TEXT,
            file_path TEXT,
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

def export_titles_to_json(json_path):
    import json

    with open(json_path, "r", encoding="utf-8") as f:
        games = json.load(f)

    with get_db() as con:

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

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            games,
            f,
            indent=2,
            ensure_ascii=False
        )

    return updated

def import_games_json(json_path):
    """
    Import Xenia Manager games.json
    """

    json_path = Path(json_path)

    if not json_path.exists():
        raise FileNotFoundError(json_path)

    with open(json_path, "r", encoding="utf-8") as f:
        games = json.load(f)

    with get_db() as con:

        for game in games:

            game_id = game.get("game_id")
            title = game.get("title")

            file_path = (
                game.get("file_locations", {})
                .get("game")
            )

            con.execute("""
            INSERT INTO games
            (
                game_id,
                title,
                file_path
            )
            VALUES (?, ?, ?)
            """, (
                game_id,
                title,
                file_path
            ))

    print(f"Imported {len(games)} games")


def import_multidisc_json(json_path):
    """
    Import preservation metadata JSON
    """

    json_path = Path(json_path)

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    entries = data["entries"]

    with get_db() as con:

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

    print(
        f"Imported multi-disc metadata "
        f"for {len(entries)} games"
    )


def search_games(search_text=""):

    with get_db() as con:

        if search_text:

            return con.execute("""
            SELECT *
            FROM games
            WHERE title LIKE ?
            ORDER BY title
            """, (
                f"%{search_text}%",
            )).fetchall()

        return con.execute("""
        SELECT *
        FROM games
        ORDER BY title
        """).fetchall()


def get_discs(title_id):

    with get_db() as con:

        return con.execute("""
        SELECT *
        FROM discs
        WHERE title_id = ?
        ORDER BY disc_index
        """, (
            title_id,
        )).fetchall()


if __name__ == "__main__":

    init_db()

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