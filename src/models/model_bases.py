from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Protocol

from PySide6.QtCore import Signal, QAbstractTableModel, QModelIndex

from db import Game, XboxGame, Xbox360Game


class BaseGameTableModel(QAbstractTableModel):
    log = Signal(str, bool, bool, bool)

    COLUMNS = []

    def __init__(self, games=None, parent=None):
        super().__init__(parent)
        self.games = games or []

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(self.games)

    def columnCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(self.COLUMNS)

    def get_game(self, row_index: int) -> Game:
        return self.games[row_index]

    def get_game_title(self, row_index: int) -> str | None:
        return self.get_game(row_index).title

    def get_game_id(self, row_index: int) -> str | None:
        return self.get_game(row_index).game_id
