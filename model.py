# model.py

from datetime import datetime

from typing import cast, Any
from PySide6.QtCore import (
    Qt,
    QAbstractTableModel,
    QModelIndex
)

from db import get_db
from utils import star

DisplayRole = Qt.ItemDataRole.DisplayRole
ToolTipRole = Qt.ItemDataRole.ToolTipRole

class GameTableModel(QAbstractTableModel):

    HEADERS = [
        "Game No."
        "Favourite",
        "Title",
        "Game ID",
        "Media ID",
        "Discs",
        "Type",
        "Last Played",
        "Play Count"
    ]

    COLUMNS = [
        ("favourite", "Fav"),
        ("game_no", "Game No."),
        ("title", "Title"),
        ("game_id", "Game ID"),
        ("media_id", "Media ID"),
        ("disc_count", "Discs"),
        ("disc_type", "Type"),
        ("last_played", "Last Played"),
        ("play_count", "Plays"),
        ("play_time", "Play Time")
    ]

    def __init__(self):
        super().__init__()

        from typing import Any

        self.games: list[dict[str, Any]] = []
        self.load()

    def load(self, search_text=""):

        with get_db() as con:
            query = """
                SELECT
                    game_no,
                    game_id,
                    media_id,
                    title,
                    file_path,
                    config_path,
                    favourite,
                    last_played,
                    play_count,
                    disc_count,
                    disc_type,
                    play_time
                FROM games
            """

            params = ()

            if search_text:
                query += " WHERE title LIKE ?"
                params = (f"%{search_text}%",)

            query += " ORDER BY title"

            self.games = cast(
                list[dict[str, Any]],
                [dict(row) for row in con.execute(query, params)]
            )
        self.layoutChanged.emit()

    def rowCount(self, parent=QModelIndex()):
        return len(self.games)

    def columnCount(self, parent=None):
        return len(self.COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None

        if orientation == Qt.Orientation.Horizontal:
            return self.COLUMNS[section][1]

        return section + 1

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):

        if not index.isValid():
            return None

        row = self.games[index.row()]
        key = self.COLUMNS[index.column()][0]

        if role == Qt.ItemDataRole.DisplayRole:

            value = row.get(key, None)

            if key == "favourite":
                return star(int(value or 0))

            if key == "disc_type":
                return value or "Single Disc"

            if key == "last_played":
                return value or ""

            if key == "play_time":
                if value is None:
                    return ""

                play_time: float = float(value)

                if play_time <= 0:
                    return "Never Played"

                play_time_int = int(play_time)

                hours, minutes = divmod(play_time_int, 60)

                if hours:
                    return f"{hours}h {minutes}m"

                return f"{minutes}m"

            return value if value is not None else ""

        if role == Qt.ItemDataRole.ToolTipRole:
            if key == "title":
                return row.get("file_path", "")

        return None

    def toggle_favourite(self, row_index):

        if row_index < 0 or row_index >= len(self.games):
            return

        row = self.games[row_index]
        game_id = row["game_id"]

        new_value = 0 if int(row.get("favourite", 0)) else 1

        with get_db() as con:
            con.execute("""
                UPDATE games
                SET favourite = ?
                WHERE game_id = ?
            """, (new_value, game_id))

        # update memory
        row["favourite"] = new_value

        # notify Qt properly
        index = self.index(row_index, 0)
        self.dataChanged.emit(index, index, [Qt.ItemDataRole.DisplayRole])

    def add_play_time(self, game_id, minutes):
        with get_db() as con:
            con.execute("""
                UPDATE games
                SET play_time = COALESCE(play_time, 0) + ?
                WHERE game_id = ?
            """, (minutes, game_id))

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
        return self.games[row_index].get("file_path", "")

    def get_game_id(self, row_index):
        return self.games[row_index].get("game_id", "")

    def get_media_id(self, row_index):
        return self.games[row_index].get("media_id", "")

    def get_config_path(self, row_index):
        return self.games[row_index].get("config_path", "")

    def sort(self, column, order=Qt.SortOrder.AscendingOrder):

        reverse = (order == Qt.SortOrder.DescendingOrder)

        mapping = {
            0: "favourite",
            1: "game_no",
            2: "title",
            3: "game_id",
            4: "media_id",
            5: "disc_count",
            6: "disc_type",
            7: "last_played",
            8: "play_count",
            9: "play_time"
        }

        field = mapping.get(column)

        if not field:
            return

        with get_db() as con:
            query = (f"""
                SELECT
                    game_no,
                    game_id,
                    media_id,
                    title,
                    file_path,
                    config_path,
                    favourite,
                    last_played,
                    play_count,
                    disc_count,
                    disc_type,
                    play_time
                FROM games
                ORDER BY {field} {"DESC" if reverse else "ASC"}
            """)
            params = ()
            self.games = cast(
                list[dict[str, Any]],
                [dict(row) for row in con.execute(query, params)]
            )
        self.layoutChanged.emit()