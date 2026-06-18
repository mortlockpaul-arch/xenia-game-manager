# main.py
import sys
from PySide6.QtWidgets import QApplication

from src.db import get_db
from src.ui import GameLauncher


def game_count():
    with get_db() as con:
        return con.execute(
            "SELECT COUNT(*) FROM games"
        ).fetchone()[0]

def main():
    app = QApplication(sys.argv)
    window = GameLauncher()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()