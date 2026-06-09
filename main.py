# main.py
import json
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from db import init_db, get_db, import_games_json
from ui import GameLauncher, GAMES_JSON


def game_count():
    with get_db() as con:
        return con.execute(
            "SELECT COUNT(*) FROM games"
        ).fetchone()[0]

def main():
    init_db()

    if game_count() == 0:
        import_games_json(
            GAMES_JSON, log_callback=GameLauncher.log
        )
    app = QApplication(sys.argv)

    window = GameLauncher()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()