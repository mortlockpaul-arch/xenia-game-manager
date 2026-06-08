# model.py

from datetime import datetime

from PySide6.QtCore import (
    Qt,
    QAbstractTableModel,
    QModelIndex
)

from db import get_db
from utils import star


class GameTableModel(QAbstractTableModel):

    HEADERS = [
        "Favourite",
        "Title",
        "Game ID",
        "Discs",
        "Type",
        "Last Played",
        "Play Count"
    ]

    def __init__(self):
        super().__init__()

        self.games = []
        self.load()

    def load(self, search_text=""):

        with get_db() as con:

            if search_text:

                self.games = con.execute("""
                    SELECT
                        game_id,
                        title,
                        file_path,
                        favourite,
                        last_played,
                        play_count,
                        disc_count,
                        disc_type
                    FROM games
                    WHERE title LIKE ?
                    ORDER BY title
                """, (
                    f"%{search_text}%",
                )).fetchall()

            else:

                self.games = con.execute("""
                    SELECT
                        game_id,
                        title,
                        file_path,
                        favourite,
                        last_played,
                        play_count,
                        disc_count,
                        disc_type
                    FROM games
                    ORDER BY title
                """).fetchall()

        self.layoutChanged.emit()

    def rowCount(self, parent=QModelIndex()):
        return len(self.games)

    def columnCount(self, parent=QModelIndex()):
        return len(self.HEADERS)

    def headerData(
        self,
        section,
        orientation,
        role
    ):
        if (
            role == Qt.DisplayRole
            and orientation == Qt.Horizontal
        ):
            return self.HEADERS[section]

        return None

    def data(self, index, role):

        if not index.isValid():
            return None

        row = self.games[index.row()]

        if role == Qt.DisplayRole:

            col = index.column()

            if col == 0:
                return star(row["favourite"])

            if col == 1:
                return row["title"]

            if col == 2:
                return row["game_id"]

            if col == 3:
                return row["disc_count"]

            if col == 4:
                return row["disc_type"] or "Single Disc"

            if col == 5:
                return row["last_played"] or ""

            if col == 6:
                return row["play_count"]

        return None

    def toggle_favourite(self, row_index):

        row = self.games[row_index]

        new_value = 0 if row["favourite"] else 1

        with get_db() as con:

            con.execute("""
                UPDATE games
                SET favourite = ?
                WHERE game_id = ?
            """, (
                new_value,
                row["game_id"]
            ))

        self.load()

    def mark_played(self, game_id):

        timestamp = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        with get_db() as con:

            con.execute("""
                UPDATE games
                SET
                    play_count = play_count + 1,
                    last_played = ?
                WHERE game_id = ?
            """, (
                timestamp,
                game_id
            ))

    def get_game_path(self, row_index):

        return self.games[row_index]["file_path"]

    def get_game_id(self, row_index):

        return self.games[row_index]["game_id"]

    def sort(
        self,
        column,
        order=Qt.AscendingOrder
    ):

        reverse = (
            order == Qt.DescendingOrder
        )

        mapping = {
            0: "favourite",
            1: "title",
            2: "game_id",
            3: "disc_count",
            4: "disc_type",
            5: "last_played",
            6: "play_count",
        }

        field = mapping.get(column)

        if not field:
            return

        with get_db() as con:

            self.games = con.execute(f"""
                SELECT
                    game_id,
                    title,
                    file_path,
                    favourite,
                    last_played,
                    play_count,
                    disc_count,
                    disc_type
                FROM games
                ORDER BY {field}
                {"DESC" if reverse else "ASC"}
            """).fetchall()

        self.layoutChanged.emit()