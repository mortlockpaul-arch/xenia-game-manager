# main.py
import sys
from PySide6.QtWidgets import QApplication

from db import Database
from ui import GameLauncher


def game_count():
    db = Database()
    db.init_db()
    with db.get_db() as con:
        return con.execute(
            "SELECT COUNT(*) FROM games"
        ).fetchone()[0]
def disc_count():
    db = Database()
    db.init_db()
    with db.get_db() as con:
        return con.execute(
            "SELECT COUNT(*) FROM discs"
        ).fetchone()[0]
def main():
    app = QApplication(sys.argv)
    print(game_count())
    print(disc_count())
    window = GameLauncher()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()