# ui.py
import shutil
import subprocess
from pathlib import Path

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTableView,
    QMessageBox,
    QHeaderView, QPlainTextEdit,
)
from PySide6.QtWidgets import QMenu
from PySide6.QtGui import QGuiApplication

from model import GameTableModel
from db import get_db, init_db, import_games_json, export_titles_to_json, import_multidisc_json
from utils import smart_title_case

XENIA_EXE = (
    r"D:\RetroBat\emulators\xenia-manager\Emulators\Xenia Canary\xenia_canary.exe"
)

GAMES_JSON = r"D:\RetroBat\emulators\xenia-manager\Config\games.json"


class GameLauncher(QWidget):

    def __init__(self):
        super().__init__()

        self.import_btn = None
        self.fix_titles_btn = None
        self.search = None
        self.table = None
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
            "Import Xenia Manager Game List"
        )

        self.import_btn.clicked.connect(
            self.import_games
        )

        toolbar.addWidget(
            self.import_btn
        )

        self.export_btn = QPushButton(
            "Update Xenia Manager Game List"
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

        header = self.table.horizontalHeader()

        header.setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive
        )

        header.setStretchLastSection(True)

        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # Game Title
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

        self.search.setClearButtonEnabled(True)
        self.table.verticalHeader().hide()

        layout.addWidget(self.table)

        self.console = QPlainTextEdit()

        self.console.setReadOnly(True)

        self.console.setMaximumHeight(100)

        self.console.setPlaceholderText(
            "Application log..."
        )

        layout.addWidget(self.console)

        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_table_menu)

        self.apply_style()

    def show_table_menu(self, pos):
        index = self.table.indexAt(pos)
        if not index.isValid():
            return

        menu = QMenu(self)

        copy_cell_action = menu.addAction("Copy Cell")
        copy_row_action = menu.addAction("Copy Row")
        copy_column_action = menu.addAction("Copy Column")

        action = menu.exec(self.table.viewport().mapToGlobal(pos))

        if not action:
            return

        model = self.table.model()
        clipboard = QGuiApplication.clipboard()

        # -------------------------
        # Copy Cell
        # -------------------------
        if action == copy_cell_action:
            clipboard.setText(
                str(model.data(index, Qt.ItemDataRole.DisplayRole))
            )
        # -------------------------
        # Copy Row
        # -------------------------
        elif action == copy_row_action:
            row = index.row()
            values = [
                str(model.index(row, col).data())
                for col in range(model.columnCount())
            ]
            clipboard.setText("\t".join(values))

        # -------------------------
        # Copy Column
        # -------------------------
        elif action == copy_column_action:
            col = index.column()
            values = [
                str(model.index(row, col).data())
                for row in range(model.rowCount())
            ]
            clipboard.setText("\n".join(values))

    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.console.appendPlainText(
            f"[{timestamp}] {message}"
        )
        return None

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
            import_games_json(GAMES_JSON, log_callback=self.log)

            # Refresh table
            self.model.load()

            message = "Import Complete. games.json imported successfully."
            self.log(message)

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
        from pathlib import Path

        BASE_DIR = Path(
            r"D:\RetroBat\emulators\xenia-manager"
        )
        config = self.model.get_config_path(
            row
        )
        if config:
            config = str(
                BASE_DIR / config
            )
        print([
            XENIA_EXE,
            path,
            config
        ])

        if not path:
            QMessageBox.warning(
                self,
                "Missing Path",
                "No game file path stored."
            )
            return
        from pathlib import Path

        if config and not Path(config).exists():
            print("Config missing:", config)

        active = Path(XENIA_EXE).parent / "xenia-canary.config.toml"
        shutil.copy(config, active)

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
