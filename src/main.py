import os
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
from db import Database
from ui import GameLauncher
import sys


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

    if False: enable_fault_handler()

    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon("assets/icons/app.ico"))
    window = GameLauncher()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()