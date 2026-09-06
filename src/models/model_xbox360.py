import re
from datetime import datetime
from pathlib import Path
from typing import cast, Any

from PySide6.QtCore import ( Qt, QModelIndex )
from PySide6.QtGui import QBrush, QColor, QFont, QIcon

from config import load_config
from db import Database, Xbox360Game, Platform
from models.model_bases import DiscGameTableModel
from utils import star, format_disc_type

DisplayRole = Qt.ItemDataRole.DisplayRole
ToolTipRole = Qt.ItemDataRole.ToolTipRole

class Xbox360GameTableModel(DiscGameTableModel):
    COLUMNS = [
        ("favourite", "Fav"),
        ("artwork_path", ""),
        ("title", "Title"),
        ("game_id", "Title ID"),
        ("media_id", "Media ID"),
        ("disc_count", "Discs"),
        ("disc_type", "Type"),
        ("last_played", "Last Played"),
        ("play_count", "Plays"),
        ("play_time", "Play Time"),
        ("disc_number", "Disc"),
        ("emulator_version", "Xenia Version"),
        ("compatibility_rating", "Compatibility"),
        ("platform", "Platform")
    ]

    def refresh_artwork(self) -> None:
        row_count = self.rowCount()

        if row_count == 0:
            return

        artwork_col = next(
            i
            for i, (key, _) in enumerate(self.COLUMNS)
            if key == "artwork_path"
        )

        top_left = self.index(0, artwork_col)
        bottom_right = self.index(row_count - 1, artwork_col)

        self.dataChanged.emit(
            top_left,
            bottom_right,
            [Qt.ItemDataRole.DecorationRole],
        )

    def __init__(self):
        super().__init__()

        self.db = Database()
        self.games: list[Xbox360Game] = []
        self.config = load_config()
        self.xenia_manager_path = Path(self.config["xenia_manager_path"])
        self.load()

    def reload_config(self):
        self.config = load_config()
        self.xenia_manager_path = Path(self.config["xenia_manager_path"])

    @staticmethod
    def normalise_disc_number(title: str) -> str:
        disc_number = re.compile(r"\(Disc\s+\d+\)", re.IGNORECASE, )
        return disc_number.sub(
            "(Disc 1)",
            title,
        )

    def get_artwork_path(self, row):

        def normalise_artwork_title(artwork_title_string: str) -> str:
            replacements = {
                ":": " - ",
                "™": "",
            }

            for old, new in replacements.items():
                artwork_title_string = artwork_title_string.replace(old, new)

            # Remove duplicate spaces
            artwork_title_string = " ".join(artwork_title_string.split())

            return artwork_title_string.strip()

        disc_suffix = re.compile(
            r"\s*-\s*Disc\s+\d+\s*-\s*.*$",
            re.IGNORECASE,
        )
        title = cast(str, row.title)

        if not title:
            return None

        title_remap_icon = {
            "SEGA Rally™ Online Arcade": "SEGA Rally",
            "Perfect Dark Zero™": "Perfect Dark Zero",
            "Geometry Wars™: Retro Evolved": "Geometry Wars Retro Evolved",
            "JoJo's Bizarre Adventure HD Ver.": "JOJOS BIZARRE ADVENTURE HD Ver",
            # Specific exception
            "Metal Gear Solid V: The Phantom Pain (Disc 1)":
                "Metal Gear Solid V - The Phantom Pain (Disc 1)",
        }

        # Apply manual remaps first
        artwork_title = title_remap_icon.get(title, title)

        # Fix punctuation differences
        artwork_title = normalise_artwork_title(
            artwork_title
        )

        base_title = disc_suffix.sub(" (Disc 1)", artwork_title, ).strip()
        base_title = self.normalise_disc_number(base_title)

        if base_title != title:
            message = f"Normalising artwork: '{title}' -> '{base_title}'"
            self.log.emit(message, False, True, False)

        icon = (self.xenia_manager_path / "GameData" / base_title / "Artwork" / "icon.ico")

        if not icon.exists():
            message = f"Icon not found: '{base_title}'"
            self.log.emit(message, False, True, False)
        return icon if icon.exists() else None

    def load(self, search_text=""):
        platform = Platform.XBOX360

        with self.db.get_db() as con:
            query = """
                SELECT *
                FROM game_view
                WHERE platform = ?
            """

            params = [platform.value]

            if search_text:
                query += " AND title LIKE ?"
                params.append(f"%{search_text}%")

            query += " ORDER BY title"

            rows = con.execute(query, params)

            self.games = [
                Xbox360Game.from_row(row)
                for row in rows
            ]

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

    def get_value(self, game: Xbox360Game, key: str):
        disc_fields = {
            "media_id",
            "file_path",
            "disc_count",
            "disc_type",
            "disc_swap_required",
            "disc_number",
            "label",
        }

        if key in disc_fields:
            if not game.discs:
                return None

            return getattr(game.discs[0], key, None)

        return getattr(game, key, None)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        compatibility = {
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
            rating = self.get_value(row, key=key)
            text, colour = compatibility.get(rating, compatibility[None])

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

        if role == Qt.ItemDataRole.DecorationRole:
            if key == "artwork_path":
                icon_path = self.get_artwork_path(row)

                if icon_path:
                    return QIcon(str(icon_path))

        if role == Qt.ItemDataRole.DisplayRole:
            value = self.get_value(row, key=key)

            if value is None:
                return ""

            if key == "platform":
                if isinstance(value, Platform):
                    return value.name
                return str(value)

            if key == "artwork_path":
                return ""

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
                paths = self.get_game_paths(index.row())
                return "\n".join(str(path) for path in paths)
        return None

    def get_game_paths(self, row_index: int) -> list[Path]:
        game = self.get_game(row_index)

        return [
            disc.file_path
            for disc in game.discs
            if disc.file_path is not None
        ]

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
                UPDATE gameplay
                SET play_time = COALESCE(play_time, 0) + ?
                WHERE game_id = ?
            """, (minutes, game_id))

    def mark_played(self, game_id):

        timestamp = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        with self.db.get_db() as con:
            con.execute("""
                UPDATE gameplay
                SET
                    play_count = play_count + 1,
                    last_played = ?
                WHERE game_id = ?
            """, (
                timestamp,
                game_id
            ))


    def sort(self, column, order=Qt.SortOrder.AscendingOrder):

        reverse = (order == Qt.SortOrder.DescendingOrder)

        mapping = {
            0: "favourite",
            2: "title",
            3: "game_id",
            4: "media_id",
            5: "disc_count",
            6: "disc_type",
            7: "last_played",
            8: "play_count",
            9: "play_time",
            10: "disc_number",
            11: "xenia_version",
            12: "compatibility_rating",
        }

        field = mapping.get(column)
        if field is None:
            return

        direction = "DESC" if reverse else "ASC"

        with self.db.get_db() as con:
            query = f"""
                    SELECT *
                    FROM game_view
                    ORDER BY {field} {direction}
                """
            params = ()
            rows = con.execute(query, params)
            self.games = [
                Xbox360Game.from_dict(dict(row))
                for row in rows
            ]
        self.layoutChanged.emit()
