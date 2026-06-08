# import_multidisc.py

import json
from pathlib import Path

from db import get_db


def import_multidisc_json(json_file):
    """
    Import Xbox 360 multi-disc metadata.
    """

    json_file = Path(json_file)

    if not json_file.exists():
        raise FileNotFoundError(json_file)

    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    entries = data.get("entries", [])

    imported = 0

    with get_db() as con:

        for entry in entries:

            title_id = entry["title_id"]

            game = con.execute(
                """
                SELECT game_id
                FROM games
                WHERE game_id = ?
                """,
                (title_id,)
            ).fetchone()

            if not game:
                continue

            con.execute(
                """
                UPDATE games
                SET
                    disc_count = ?,
                    disc_type = ?,
                    xenia_disc_swap_required = ?
                WHERE game_id = ?
                """,
                (
                    entry["disc_count"],
                    entry["disc_type"],
                    int(entry["xenia_disc_swap_required"]),
                    title_id,
                ),
            )

            con.execute(
                """
                DELETE FROM discs
                WHERE title_id = ?
                """,
                (title_id,),
            )

            for disc_index, disc_label in enumerate(
                entry["disc_layout"],
                start=1,
            ):

                con.execute(
                    """
                    INSERT INTO discs
                    (
                        title_id,
                        disc_index,
                        label,
                        file_path
                    )
                    VALUES (?, ?, ?, NULL)
                    """,
                    (
                        title_id,
                        disc_index,
                        disc_label,
                    ),
                )

            imported += 1

    print(f"Imported metadata for {imported} games")


def get_game_discs(title_id):
    """
    Return disc information for UI detail panel.
    """

    with get_db() as con:

        return con.execute(
            """
            SELECT
                disc_index,
                label,
                file_path
            FROM discs
            WHERE title_id = ?
            ORDER BY disc_index
            """,
            (title_id,),
        ).fetchall()


def get_multidisc_games():

    with get_db() as con:

        return con.execute(
            """
            SELECT
                game_id,
                title,
                disc_count,
                disc_type
            FROM games
            WHERE disc_count > 1
            ORDER BY title
            """
        ).fetchall()

if __name__ == "__main__":

    import_multidisc_json(
        r"multidisc.json"
    )

    print("Done")