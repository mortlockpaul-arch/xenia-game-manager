import faulthandler
from pathlib import Path

def enable_fault_handler():
    fault_log = Path(__file__).resolve().parent / "logs" / "faulthandler.log"

    fault_file = fault_log.open("w", encoding="utf-8")

    faulthandler.enable(fault_file)



import os

import sys
from PySide6.QtGui import QIcon

from PySide6.QtWidgets import QApplication

from db import Database
from ui import GameLauncher
from line_profiler_pycharm import profile


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

@profile
def main():

    if False: enable_fault_handler()

    app = QApplication(sys.argv)

    print("1 - QApplication created")

    app.setWindowIcon(QIcon("assets/icons/app.ico"))

    print("2 - icon set")

    print("Games:", game_count())
    print("Discs:", disc_count())
    print("PID:", os.getpid())

    print("3 - creating GameLauncher")
    window = GameLauncher()

    print("4 - GameLauncher created")

    window.show()

    print("5 - window shown")

    sys.exit(app.exec())

if __name__ == "__main__":
    main()