from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Protocol

from PySide6.QtCore import Signal, QAbstractTableModel, QModelIndex

from db import Game, XboxGame, Xbox360Game

class GameModel(Protocol):
    games: list[Game]

    def get_game(self, row_index: int) -> Game:
        ...

    def get_game_title(self, row_index: int) -> str:
        ...

    def get_game_id(self, row_index: int) -> str:
        ...

    def get_game_path(self, row_index: int) -> Path | None:
        ...

    def get_game_paths(self, row_index: int) -> list[Path]:
        ...

    def get_media_id(self, row_index: int) -> str | None:
        ...

    def get_config_path(self, row_index: int) -> Path | None:
        ...

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

    def get_game_title(self, row_index: int) -> str:
        return self.get_game(row_index).title

    def get_game_id(self, row_index: int) -> str:
        return self.get_game(row_index).game_id

class DiscGameTableModel(BaseGameTableModel):

    def get_game_path(self, row_index: int) -> Path | None:
        game = self.get_game(row_index)

        if not game.discs:
            return None

        return game.discs[0].file_path

    def get_game_paths(self, row_index: int) -> list[Path]:
        game = self.get_game(row_index)

        return [
            disc.file_path
            for disc in game.discs
            if disc.file_path is not None
        ]

    def get_media_id(self, row_index: int) -> str | None:
        game = self.get_game(row_index)

        if not game.discs:
            return None

        return game.discs[0].media_id