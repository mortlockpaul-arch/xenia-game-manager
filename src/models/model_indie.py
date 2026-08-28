import re
from datetime import datetime
from pathlib import Path
from typing import cast, Any

from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, Signal, QSize
from PySide6.QtGui import QBrush, QColor, QFont, QIcon
from PySide6.QtWidgets import QPushButton

from config import load_config_file
from db import Database, XBLIGGame, XboxGame, Platform, Game
from models.model_bases import BaseGameTableModel
from utils import star, format_disc_type

DisplayRole = Qt.ItemDataRole.DisplayRole
ToolTipRole = Qt.ItemDataRole.ToolTipRole

class IndieGameTableModel(BaseGameTableModel):

    COLUMNS = [
        ("icon", "Icon"),
        ("title", "Title"),
        ("game_id", "Title ID"),
        ("publisher", "Publisher"),
        ("content_converted", "Content Converted"),
        ("content_format", "Content Format"),
        ("extracted", "Extracted"),
        ("decompiled", "Decompiled"),
        ("executables", "Executables"),
        ("dll_files", "DLL Files"),
        ("platform", "Platform"),
    ]

    def __init__(self, games=None, parent=None):
        super().__init__(games or [], parent)

        self.config = load_config_file()
        self.indie_games_path = Path(
            self.config["indie_games_path"]
        )

        self.db = Database()

    def reload_config(self):
        self.config = load_config_file()
        self.indie_games_path = Path(
            self.config["indie_games_path"]
        )

    def set_games(self, games):
        self.beginResetModel()
        self.games = list(games)
        self.endResetModel()

    def get_value(self, game: XBLIGGame, key: str):
        return getattr(game, key, None)

    def headerData(
            self,
            section,
            orientation,
            role=Qt.ItemDataRole.DisplayRole,
    ):
        if role != Qt.ItemDataRole.DisplayRole:
            return None

        if orientation == Qt.Orientation.Horizontal:
            if 0 <= section < len(self.COLUMNS):
                return self.COLUMNS[section][1]

            return None

        if orientation == Qt.Orientation.Vertical:
            return section + 1

        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        game = self.games[index.row()]
        key = self.COLUMNS[index.column()][0]

        # ----------------------------------------
        # Return the actual game
        # ----------------------------------------

        if role == Qt.ItemDataRole.UserRole:
            return game

        # ----------------------------------------
        # Artwork
        # ----------------------------------------

        if key == "icon":
            if role == Qt.ItemDataRole.DecorationRole:
                if game.icon and game.icon.exists():
                    return QIcon(str(game.icon))

                if game.extracted:
                    icon = game.extracted / "DashboardIcon.png"

                    if icon.exists():
                        return QIcon(str(icon))

            if role == Qt.ItemDataRole.DisplayRole:
                return ""

        # ----------------------------------------
        # Display
        # ----------------------------------------

        if role == Qt.ItemDataRole.DisplayRole:

            if key == "platform":
                return game.platform.display_name

            if key == "extracted":
                return "Yes" if game.extracted else "No"

            if key == "decompiled":
                return (
                    game.decompiled.name
                    if game.decompiled
                    else ""
                )

            if key == "executables":
                return str(len(game.executables or []))

            if key == "dll_files":
                return str(len(game.dll_files or []))

            value = self.get_value(game, key)

            if value is None:
                return ""

            if isinstance(value, Path):
                return str(value)

            return str(value)

        # ----------------------------------------
        # Tooltips
        # ----------------------------------------

        if role == Qt.ItemDataRole.ToolTipRole:

            if key == "title":
                paths = self.get_game_paths(index.row())

                if paths:
                    return "\n".join(
                        str(path)
                        for path in paths
                    )

            if key == "icon" and game.icon:
                return str(game.icon)

        return None

    def get_game_paths(self, row_index: int) -> list[Path]:
        game = self.get_game(row_index)

        paths = []

        if game.package:
            paths.append(game.package)

        if game.extracted:
            paths.append(game.extracted)

        if game.game_root:
            paths.append(game.game_root)

        return paths

    def sort(
        self,
        column,
        order=Qt.SortOrder.AscendingOrder,
    ):
        if column < 0 or column >= len(self.COLUMNS):
            return

        key = self.COLUMNS[column][0]
        reverse = order == Qt.SortOrder.DescendingOrder

        def sort_value(game):
            value = self.get_value(game, key)

            if value is None:
                return ""

            if isinstance(value, list):
                return len(value)

            if isinstance(value, Path):
                return str(value).casefold()

            if isinstance(value, Platform):
                return value.value.casefold()

            return str(value).casefold()

        self.layoutAboutToBeChanged.emit()

        self.games.sort(
            key=sort_value,
            reverse=reverse,
        )

        self.layoutChanged.emit()