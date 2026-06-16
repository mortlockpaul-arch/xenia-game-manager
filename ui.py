# ui.py
import shutil
import subprocess
import threading
from datetime import datetime
from pathlib import Path

import time

from PySide6.QtCore import Qt, QEasingCurve, QPropertyAnimation, QRect
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTableView,
    QMessageBox,
    QHeaderView, QPlainTextEdit, QGroupBox, QLabel, QSizePolicy, QMainWindow, QFormLayout, QToolButton, QFileDialog,
    QFrame, QGraphicsDropShadowEffect, QProgressBar,
)
from PySide6.QtWidgets import QMenu
from PySide6.QtGui import QGuiApplication

import xboxtupdater
from config import save_config, load_config, XENIA_EXE, GAMES_JSON, XENIA_BASE_DIR
from model import GameTableModel
from db import get_db, init_db, import_games_json, export_titles_to_json, import_multidisc_json, clear_db
from utils import smart_title_case
from xboxtupdater import XboxTUMApp
from xboxunity_api import login_xboxunity, test_connectivity

class ClickOverlay(QWidget):
    def __init__(self, launcher):
        super().__init__(launcher)
        self.launcher = launcher

    def mousePressEvent(self, event):
        self.launcher.close_drawer()

class GameLauncher(QMainWindow):

    def __init__(self):
        super().__init__()
        self.process = None
        self.start_time = None
        self.token = None
        self.progress = None
        self.login_btn = None
        self.entry_apikey = None
        self.entry_pass = None
        self.entry_user = None
        self.xenia_canary_path = None
        self.export_btn = None
        self.xenia_path = None
        self.settings_panel = None
        self.settings_btn = None
        self.drawer_open = False
        self.drawer_anim = None
        self.overlay = None
        self.settings_drawer = None
        self.import_btn = None
        self.fix_titles_btn = None
        self.search = None
        self.table = None
        self.setWindowTitle(
            "Xenia SQLite Launcher"
        )
        init_db()
        self.model = GameTableModel()
        self.resize(1800, 700)
        self.build_ui()
        self.import_games()
        self.load_saved_config()

    def create_settings_drawer(self):

        self.overlay = ClickOverlay(self)
        self.overlay.setStyleSheet("background-color: rgba(0,0,0,120);")
        self.overlay.hide()

        self.settings_drawer = QFrame(self)
        self.settings_drawer.setObjectName("settingsDrawer")
        self.settings_drawer.setFixedWidth(420)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(40)
        shadow.setOffset(-5, 0)
        self.settings_drawer.setGraphicsEffect(shadow)

        self.settings_drawer.setStyleSheet("""
            QFrame#settingsDrawer {
                background-color: #1b1b1b;
                border-left: 1px solid #333;
            }
        """)

        layout = QVBoxLayout(self.settings_drawer)

        title = QLabel("Settings")
        layout.addWidget(title)

        # ---------------- LOGIN BOX ----------------
        login_box = QGroupBox("Login XboxUnity / API Key")
        login_box.setMaximumWidth(380)

        login_form = QFormLayout()

        self.entry_user = QLineEdit()
        self.entry_pass = QLineEdit()
        self.entry_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.entry_apikey = QLineEdit()

        self.entry_user.setPlaceholderText("Username")
        self.entry_pass.setPlaceholderText("Password")
        self.entry_apikey.setPlaceholderText("API Key")

        login_form.addRow("Username", self.entry_user)
        login_form.addRow("Password", self.entry_pass)
        login_form.addRow("API Key", self.entry_apikey)

        self.login_btn = QPushButton("Login")
        self.login_btn.clicked.connect(self.login)
        login_form.addRow(self.login_btn)

        login_box.setLayout(login_form)

        login_box.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed
        )

        layout.addWidget(
            login_box,
            alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )

        # ---------------- XENIA PATH ----------------
        layout.addWidget(QLabel("Xenia Manager Folder"))

        xenia_row = QHBoxLayout()
        self.xenia_path = QLineEdit()
        self.xenia_path.setPlaceholderText("Xenia Manager location...")

        browse_btn_xenia = QPushButton("Browse")
        browse_btn_xenia.clicked.connect(self.pick_xenia_path)

        xenia_row.addWidget(self.xenia_path)
        xenia_row.addWidget(browse_btn_xenia)

        layout.addLayout(xenia_row)

        # ---------------- XENIA CANARY PATH ----------------
        layout.addWidget(QLabel("Xenia Canary Folder"))

        canary_row = QHBoxLayout()
        self.xenia_canary_path = QLineEdit()
        self.xenia_canary_path.setPlaceholderText("Xenia Canary location...")

        browse_btn_canary = QPushButton("Browse")
        browse_btn_canary.clicked.connect(self.pick_xenia_canary_path)

        canary_row.addWidget(self.xenia_canary_path)
        canary_row.addWidget(browse_btn_canary)

        layout.addLayout(canary_row)

        # -----------------------
        # Tools
        # -----------------------

        tools_box = QGroupBox("Tools")

        tools_layout = QVBoxLayout()


        self.fix_titles_btn = QPushButton("Fix Titles")
        self.fix_titles_btn.clicked.connect(self.fix_titles)
        tools_layout.addWidget(self.fix_titles_btn)

        self.import_btn = QPushButton("Import Xenia Manager Game List")
        self.import_btn.clicked.connect(self.import_games)
        tools_layout.addWidget(self.import_btn)

        self.export_btn = QPushButton("Update Xenia Manager Game List")
        self.export_btn.clicked.connect(self.export_titles)
        tools_layout.addWidget(self.export_btn)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh)
        tools_layout.addWidget(self.refresh_btn)
        
        tools_layout.addWidget(self.fix_titles_btn)
        tools_layout.addWidget(self.import_btn)
        tools_layout.addWidget(self.export_btn)
        tools_layout.addWidget(self.refresh_btn)

        tools_box.setLayout(tools_layout)

        layout.addWidget(tools_box)

        layout.addStretch()

        self.settings_drawer.hide()

    def toggle_drawer(self):
        if self.drawer_open:
            self.close_drawer()
        else:
            self.open_drawer()

    def open_drawer(self):

        self.drawer_open = True

        self.overlay.setGeometry(self.rect())
        self.overlay.show()

        self.settings_drawer.show()

        start = QRect(
            self.width(),
            0,
            self.settings_drawer.width(),
            self.height()
        )

        end = QRect(
            self.width() - self.settings_drawer.width(),
            0,
            self.settings_drawer.width(),
            self.height()
        )

        self.drawer_anim = QPropertyAnimation(
            self.settings_drawer,
            b"geometry"
        )

        self.drawer_anim.setDuration(250)
        self.drawer_anim.setEasingCurve(
            QEasingCurve.Type.OutCubic
        )
        self.drawer_anim.setStartValue(start)
        self.drawer_anim.setEndValue(end)
        self.drawer_anim.start()

    def close_drawer(self):

        self.drawer_open = False

        start = self.settings_drawer.geometry()

        end = QRect(
            self.width(),
            0,
            self.settings_drawer.width(),
            self.height()
        )

        self.drawer_anim = QPropertyAnimation(
            self.settings_drawer,
            b"geometry"
        )

        self.drawer_anim.setDuration(200)
        self.drawer_anim.setEasingCurve(
            QEasingCurve.Type.InCubic
        )
        self.drawer_anim.setStartValue(start)
        self.drawer_anim.setEndValue(end)

        self.drawer_anim.finished.connect(
            self.settings_drawer.hide
        )

        self.drawer_anim.finished.connect(
            self.overlay.hide
        )

        self.drawer_anim.start()

    def resizeEvent(self, event):

        super().resizeEvent(event)

        if self.overlay:
            self.overlay.setGeometry(self.rect())

        if self.drawer_open:
            self.settings_drawer.setGeometry(
                self.width() - self.settings_drawer.width(),
                0,
                self.settings_drawer.width(),
                self.height()
            )

    def build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        self.create_settings_drawer()
        main_layout = QVBoxLayout(central)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # ================= LOGIN =================
        from PySide6.QtWidgets import QFormLayout


        # ================= TOOLBAR =================
        toolbar = QHBoxLayout()

        self.settings_btn = QToolButton()
        self.settings_btn.setText("⚙")
        self.settings_btn.setCheckable(True)
        self.settings_btn.setChecked(False)
        self.settings_btn.clicked.connect(self.toggle_drawer)
        toolbar.addWidget(self.settings_btn)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search games...")
        self.search.textChanged.connect(self.search_changed)
        toolbar.addWidget(self.search)

        self.btn_folder = QPushButton("Select Games Folder")
        self.btn_folder.clicked.connect(self.select_folder)

        self.btn_tu = QPushButton("Search & Download TUs")
        self.btn_tu.clicked.connect(self.search_and_download_tus)

        toolbar.addWidget(self.btn_folder)
        toolbar.addWidget(self.btn_tu)

        # ================= PROGRESS =================
        self.progress = QProgressBar()
        toolbar.addWidget(self.progress)

        # 🔥 IMPORTANT: attach toolbar to main layout
        main_layout.addLayout(toolbar)

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

        main_layout.addWidget(self.table)

        self.console = QPlainTextEdit()

        self.console.setReadOnly(True)

        self.console.setMaximumHeight(100)

        self.console.setPlaceholderText(
            "Application log..."
        )

        main_layout.addWidget(self.console)

        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_table_menu)

        self.apply_style()

    def toggle_settings(self):
        self.settings_panel.setVisible(self.settings_btn.isChecked())

    def pick_xenia_path(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Xenia Manager Folder"
        )

        if folder:
            self.xenia_path.setText(folder)
            config = load_config()
            config["xenia_path"] = folder
            save_config(config)

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Games Folder")
        if folder:
            self._log(f"Selected: {folder}")

    def search_and_download_tus(self):
        if not self.model.games:
            self._err("Error", "No games loaded")
            return
        folder = QFileDialog.getExistingDirectory(self, "Select output folder")
        if not folder:
            return
        self.worker = xboxtupdater.TUDownloadWorker(
            games=self.model.games,
            token=self.token,
            api_key=self.api_key,
            output_folder=folder
        )
        self.worker.log.connect(self.log)
        self.worker.progress.connect(self.update_file_progress)
        self.worker.game_progress.connect(self.update_game_progress)
        self.worker.finished.connect(self.download_finished)

        self.worker.start()

    def update_file_progress(self, done, total):
        if total > 0:
            self.progress.setMaximum(total)
            self.progress.setValue(done)


    def update_game_progress(self, current, total):
        self.log(f"Game progress: {current}/{total}")

    def download_finished(self, stats):
        self.log("\n=== SUMMARY ===")
        self.log(f"Games: {stats['games_total']}")
        self.log(f"With TUs: {stats['games_with_tu']}")
        self.log(f"Downloaded: {stats['tus_downloaded']}")
        self.log(f"Errors: {stats['errors']}")

        self.log("Done: TU download completed")
        
    def pick_xenia_canary_path(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Xenia Canary Folder"
        )

        if folder:
            self.xenia_canary_path.setText(folder)
            config = load_config()
            config["xenia_canary_path"] = folder
            save_config(config)

    def load_saved_config(self):
        config = load_config()

        self.entry_user.setText(config.get("username", ""))
        self.entry_pass.setText(config.get("password", ""))
        self.entry_apikey.setText(config.get("api_key", ""))
        self.xenia_path.setText(config.get("xenia_path", ""))
        self.xenia_canary_path.setText(config.get("xenia_canary_path", ""))

        if config.get("api_key"):
            self.api_key = config["api_key"]

    def login(self):
        username = self.entry_user.text().strip()
        password = self.entry_pass.text().strip()
        api_key = self.entry_apikey.text().strip()

        config = load_config()

        # Save API key mode (preferred)
        if api_key:
            config["api_key"] = api_key
            config["username"] = username
            config["password"] = password
            save_config(config)

            self.api_key = api_key
            self.log("API Key saved.")

            # optional connectivity check
            try:
                if test_connectivity():
                    self.log("XboxUnity connectivity OK.")
                else:
                    self.log("WARNING: XboxUnity connectivity issue.")
            except Exception as e:
                self.log(f"Connectivity error: {e}")

            return

        # Username/password login
        if not username or not password:
            self.log("Login Error: Enter username/password or API key")
            return

        self.log("Checking XboxUnity...")

        try:
            if not test_connectivity():
                self.log("Error: Cannot reach XboxUnity")
                return
        except Exception as e:
            self.log(str(e))
            return

        self.log("Logging in...")

        token = login_xboxunity(username, password)

        if token:
            self.token = token
            self.api_key = None

            config["username"] = username
            config["password"] = password
            config.pop("api_key", None)

            save_config(config)

            self.log("Login successful.")
        else:
            self.log("Login Failed: Invalid credentials")

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

            # Refresh table
            self.model.load()

            # Import games
            import_games_json(GAMES_JSON, self.model.games, log_callback=self.log)

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


        config = self.model.get_config_path(
            row
        )
        if config:
            config = str(
                XENIA_BASE_DIR / config
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
            import subprocess
            import time
            self.start_time = time.time()
            self.process = subprocess.Popen([XENIA_EXE, path])

            threading.Thread(
                target=self.monitor_game,
                args=(game_id,),
                daemon=True
            ).start()

        except Exception as e:

            QMessageBox.critical(
                self,
                "Launch Error",
                str(e)
            )

    import time

    def monitor_game(self, game_id):
        while self.process.poll() is None:
            time.sleep(1)  # don’t burn CPU

        end_time = time.time()
        minutes = int((end_time - self.start_time) / 60)

        self.model.add_play_time(game_id, minutes)
        self.model.mark_played(game_id)
        self.model.load()
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
        
        QGroupBox {
            font-size: 14px;
            font-weight: bold;
            color: #e5e5e5;
            border: 1px solid #2a2a2a;
            border-radius: 10px;
            margin-top: 12px;
            padding: 10px;
            background-color: #1e1e1e;
        }
        
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 5px;
        }
        
        QLabel {
            color: #cfcfcf;
            font-size: 12px;
        }
        
        QLineEdit {
            background-color: #2b2b2b;
            border: 1px solid #3a3a3a;
            border-radius: 6px;
            padding: 6px 10px;
            color: #ffffff;
            selection-background-color: #0078d7;
        }
        
        QLineEdit:focus {
            border: 1px solid #0078d7;
        }
        
        QPushButton {
            background-color: #2d2d2d;
            border: 1px solid #3a3a3a;
            padding: 6px;
            border-radius: 6px;
            color: #ffffff;
        }
        
        QPushButton:hover {
            background-color: #3a3a3a;
        }
        
        QPushButton:pressed {
            background-color: #0078d7;
        }
        """)
