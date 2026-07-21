# main.py
import os

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
    import ctypes
    appid = "PaulMortlock.XeniaGameManager"
    set_appid = getattr(
        ctypes.windll.shell32,
        "SetCurrentProcessExplicitAppUserModelID",
        None,
    )
    if set_appid:
        set_appid(appid)
    app = QApplication(sys.argv)
    print(game_count())
    print(disc_count())
    print(str(os.getpid()))
    window = GameLauncher()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()