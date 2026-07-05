# model.py

from datetime import datetime

from typing import cast, Any
from PySide6.QtCore import (
    Qt,
    QAbstractTableModel,
    QModelIndex
)
from PySide6.QtGui import QBrush, QColor, QFont

from db import Database
from utils import star, format_disc_type

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
        ("game_no", "No."),
        ("title", "Title"),
        ("game_id", "Title ID"),
        ("media_id", "Media ID"),
        ("disc_count", "Discs"),
        ("disc_type", "Type"),
        ("last_played", "Last Played"),
        ("play_count", "Plays"),
        ("play_time", "Play Time"),
        ("disc_number", "Disc"),
        ("disc_type", "Disc Type"),
        ("label", "Label"),
        ("xenia_version", "Xenia Version"),
        ("compatibility_rating", "Compatibility"),
    ]

    def __init__(self):
        super().__init__()

        from typing import Any
        self.db = Database()
        self.games: list[dict[str, Any]] = []
        self.load()

    def load(self, search_text=""):

        with self.db.get_db() as con:
            query = """
                SELECT
                    game_no,
                    games.game_id,
                    media_id,
                    title,
                    file_path,
                    config_path,
                    COALESCE(favourites.favourite, 0) AS favourite,
                    last_played,
                    play_count,
                    disc_count,
                    disc_type,
                    play_time,
                    disc_number,
                    label,
                    xenia_version,
                    compatibility_rating
                FROM games LEFT JOIN discs ON discs.disc_index = games.disc_number AND discs.title_id = games.game_id
                LEFT JOIN favourites ON favourites.game_id = games.game_id
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
        COMPATIBILITY = {
            "Perfect": ("Perfect", "#2ecc71"),
            "Playable": ("Playable", "#27ae60"),
            "Gameplay": ("Gameplay", "#f1c40f"),
            "Menu": ("Menu", "#e67e22"),
            "Loads": ("Loads", "#e74c3c"),
            "Unplayable": ("Unplayable", "#7f8c8d"),
            None: ("Unknown", "#95a5a6"),
        }

        if not index.isValid():
            return None

        row = self.games[index.row()]
        key = self.COLUMNS[index.column()][0]

        # Compatibility column special roles
        if key == "compatibility_rating":
            rating = row.get("compatibility_rating")
            text, colour = COMPATIBILITY.get(rating, COMPATIBILITY[None])

            if role == Qt.ItemDataRole.DisplayRole:
                return text

            if role == Qt.ItemDataRole.ForegroundRole:
                return QBrush(QColor(colour))

            if role == Qt.ItemDataRole.TextAlignmentRole:
                return Qt.AlignmentFlag.AlignCenter

            if role == Qt.ItemDataRole.FontRole:
                font = QFont()
                font.setBold(True)
                return font

        if role == Qt.ItemDataRole.DisplayRole:
            value = row.get(key)

            if key == "favourite":
                return star(int(value or 0))

            if key == "last_played":
                return value or ""

            if key == "play_time":
                if value is None:
                    return ""

                play_time = int(cast(float, value))
                hours, minutes = divmod(play_time, 60)

                return f"{hours}h {minutes}m" if hours else f"{minutes}m"

            if key == "disc_type":
                return format_disc_type(cast(str, value)) or None

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

        with self.db.get_db() as con:
            con.execute("""
                INSERT INTO favourites (game_id, favourite)
                VALUES (?, ?)
                ON CONFLICT(game_id)
                DO UPDATE SET favourite = excluded.favourite
            """, (game_id, new_value))

        row["favourite"] = new_value

        index = self.index(row_index, 0)
        self.dataChanged.emit(index, index, [Qt.ItemDataRole.DisplayRole])

    def add_play_time(self, game_id, minutes):
        with self.db.get_db() as con:
            con.execute("""
                UPDATE games
                SET play_time = COALESCE(play_time, 0) + ?
                WHERE game_id = ?
            """, (minutes, game_id))

    def mark_played(self, game_id):

        timestamp = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        with self.db.get_db() as con:

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

    def get_game_title(self, row_index):
        return self.games[row_index].get("title", "")

    def get_game_path(self, row_index):
        return self.games[row_index].get("file_path", "")

    def get_game_id(self, row_index):
        return self.games[row_index].get("game_id", "")

    def get_media_id(self, row_index):
        return self.games[row_index].get("media_id", "")

    def get_config_path(self, row_index):
        return self.games[row_index].get("config_path", "")

    def get_xenia_version(self, row_index):
        return self.games[row_index].get("xenia_version", "")

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
            9: "play_time",
            10: "disc_number",
            11: "label",
            12: "xenia_version",
            13: "compatibility_rating",
        }

        field = mapping.get(column)

        if not field:
            return

        with self.db.get_db() as con:
            query = (f"""
                SELECT
                    game_no,
                    games.game_id,
                    media_id,
                    title,
                    file_path,
                    config_path,
                    COALESCE(favourites.favourite, 0) AS favourite,
                    last_played,
                    play_count,
                    disc_count,
                    disc_type,
                    play_time,
                    disc_number,
                    label,
                    xenia_version,
                    compatibility_rating
                FROM games LEFT JOIN discs ON discs.disc_index = games.disc_number AND discs.title_id = games.game_id
                LEFT JOIN favourites ON favourites.game_id = games.game_id
                ORDER BY {field} {"DESC" if reverse else "ASC"}
            """)
            params = ()
            self.games = cast(
                list[dict[str, Any]],
                [dict(row) for row in con.execute(query, params)]
            )
        self.layoutChanged.emit()