# ui.py

import subprocess
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTableView,
    QMessageBox,
    QHeaderView,
)

from model import GameTableModel
from db import get_db, init_db, import_games_json, export_titles_to_json
from utils import smart_title_case


XENIA_EXE = (
    r"D:\RetroBat\emulators\xenia-manager\Emulators\Xenia Canary\xenia_canary.exe"
)

GAMES_JSON = r"D:\RetroBat\emulators\xenia-manager\Config\games.json"

class GameLauncher(QWidget):

    def __init__(self):
        super().__init__()

        self.setWindowTitle(
            "Xenia SQLite Launcher"
        )

        self.resize(1200, 700)

        self.model = GameTableModel()

        self.build_ui()

    def build_ui(self):

        layout = QVBoxLayout(self)

        # -------------------------
        # Toolbar
        # -------------------------

        toolbar = QHBoxLayout()

        self.search = QLineEdit()
        self.search.setPlaceholderText(
            "Search games..."
        )
        self.search.textChanged.connect(
            self.search_changed
        )

        toolbar.addWidget(self.search)

        self.fix_titles_btn = QPushButton(
            "Fix Titles"
        )
        self.fix_titles_btn.clicked.connect(
            self.fix_titles
        )

        toolbar.addWidget(
            self.fix_titles_btn
        )

        self.import_btn = QPushButton(
            "Import games.json"
        )

        self.import_btn.clicked.connect(
            self.import_games
        )

        toolbar.addWidget(
            self.import_btn
        )

        self.export_btn = QPushButton(
            "Update games.json"
        )

        self.export_btn.clicked.connect(
            self.export_titles
        )

        toolbar.addWidget(
            self.export_btn
        )

        self.refresh_btn = QPushButton(
            "Refresh"
        )
        self.refresh_btn.clicked.connect(
            self.refresh
        )

        toolbar.addWidget(
            self.refresh_btn
        )

        layout.addLayout(toolbar)

        # -------------------------
        # Table
        # -------------------------

        self.table = QTableView()

        self.table.setModel(self.model)

        self.table.setSortingEnabled(True)

        self.table.setAlternatingRowColors(True)

        self.table.doubleClicked.connect(
            self.launch_game
        )

        self.table.clicked.connect(
            self.table_clicked
        )

        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch
        )

        layout.addWidget(self.table)

        self.apply_style()

    # -------------------------
    # Search
    # -------------------------

    def export_titles(self):

        try:

            updated = export_titles_to_json(
                GAMES_JSON
            )

            QMessageBox.information(
                self,
                "Export Complete",
                f"{updated} titles written to games.json"
            )

        except Exception as e:

            QMessageBox.critical(
                self,
                "Export Failed",
                str(e)
            )

    def search_changed(self, text):

        self.model.load(text)

    # -------------------------
    # Refresh
    # -------------------------

    def refresh(self):

        self.model.load()

    # -------------------------
    # Favourite Click
    # -------------------------

    def table_clicked(self, index):

        if index.column() == 0:
            self.model.toggle_favourite(
                index.row()
            )

    def import_games(self):


        try:

            if not Path(GAMES_JSON).exists():
                QMessageBox.warning(
                    self,
                    "Missing File",
                    GAMES_JSON
                )
                return

            # Ensure schema exists
            init_db()

            # Import games
            import_games_json(GAMES_JSON)

            # Refresh table
            self.model.load()

            QMessageBox.information(
                self,
                "Import Complete",
                "games.json imported successfully."
            )

        except Exception as e:

            QMessageBox.critical(
                self,
                "Import Failed",
                str(e)
            )

    # -------------------------
    # Launch Game
    # -------------------------

    def launch_game(self, index):

        row = index.row()

        path = self.model.get_game_path(
            row
        )

        game_id = self.model.get_game_id(
            row
        )

        if not path:

            QMessageBox.warning(
                self,
                "Missing Path",
                "No game file path stored."
            )
            return

        try:

            subprocess.Popen(
                [XENIA_EXE, path]
            )

            self.model.mark_played(
                game_id
            )

            self.model.load()

        except Exception as e:

            QMessageBox.critical(
                self,
                "Launch Error",
                str(e)
            )

    # -------------------------
    # Fix Titles
    # -------------------------

    def fix_titles(self):

        updated = 0

        with get_db() as con:

            rows = con.execute("""
                SELECT
                    game_id,
                    title
                FROM games
            """).fetchall()

            for row in rows:

                cleaned = smart_title_case(
                    row["title"]
                )

                if cleaned != row["title"]:

                    con.execute("""
                        UPDATE games
                        SET title = ?
                        WHERE game_id = ?
                    """, (
                        cleaned,
                        row["game_id"]
                    ))

                    updated += 1

        self.model.load()

        QMessageBox.information(
            self,
            "Done",
            f"Updated {updated} titles."
        )

    # -------------------------
    # Style
    # -------------------------

    def apply_style(self):

        self.setStyleSheet("""
        QWidget {
            background: #202124;
            color: white;
            font-size: 10pt;
        }

        QLineEdit {
            padding: 6px;
            background: #2d2f31;
            border: 1px solid #555;
        }

        QPushButton {
            padding: 6px;
            background: #3c4043;
            border: 1px solid #666;
        }

        QPushButton:hover {
            background: #4b5054;
        }

        QTableView {
            background: #1e1e1e;
            alternate-background-color: #292929;
            gridline-color: #444;
        }

        QHeaderView::section {
            background: #3c4043;
            padding: 6px;
            border: 1px solid #555;
        }
        """)