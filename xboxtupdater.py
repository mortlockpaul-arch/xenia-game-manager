import os
import sys
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QLineEdit, QPushButton,
    QTreeWidget, QTreeWidgetItem,
    QTextEdit, QFileDialog, QMessageBox,
    QProgressBar
)
from PySide6.QtCore import Qt
from config import save_config, load_config

from xboxunity_api import (
    login_xboxunity,
    search_tus,
    download_tu,
    test_connectivity
)

from PySide6.QtCore import QThread, Signal

class TUDownloadWorker(QThread):
    log = Signal(str)
    progress = Signal(int, int)          # current, total
    game_progress = Signal(int, int)     # game index, total games
    finished = Signal(dict)

    def __init__(self, games, token=None, api_key=None, output_folder=""):
        super().__init__()
        self.games = games
        self.token = token
        self.api_key = api_key
        self.output_folder = output_folder

    def run(self):
        total_games = len(self.games)

        stats = {
            "games_total": total_games,
            "games_with_tu": 0,
            "tus_downloaded": 0,
            "errors": 0
        }

        self.log.emit("Starting TU download process...\n")

        for game_index, game in enumerate(self.games, 1):
            game_name = game.get("title")
            media_id = game.get("media_id")
            title_id = game.get("game_id")

            self.game_progress.emit(game_index, total_games)

            self.log.emit(f"Searching TUs for: {game_name}")

            try:
                tus = search_tus(
                    media_id=media_id,
                    title_id=title_id,
                    token=self.token,
                    api_key=self.api_key
                )
            except Exception as e:
                self.log.emit(f"ERROR searching TUs: {e}")
                stats["errors"] += 1
                continue

            if not tus:
                self.log.emit(f"No TUs found for {game_name}")
                continue

            stats["games_with_tu"] += 1

            game_folder = os.path.join(
                self.output_folder,
                self._safe_name(game_name)
            )
            os.makedirs(game_folder, exist_ok=True)

            self.log.emit(f"Found {len(tus)} TUs for {game_name}")

            for tu in tus:
                filename = tu.get("fileName")
                download_url = tu.get("downloadUrl")

                destination = os.path.join(game_folder, filename)

                self.log.emit(f"Downloading {filename}")

                try:
                    success, original_file = download_tu(
                        download_url,
                        destination,
                        progress_callback=self._progress_callback
                    )

                    if success:
                        stats["tus_downloaded"] += 1
                        self.log.emit(f"Downloaded: {filename}")
                    else:
                        stats["errors"] += 1
                        self.log.emit(f"FAILED: {filename}")

                except Exception as e:
                    stats["errors"] += 1
                    self.log.emit(f"ERROR downloading {filename}: {e}")

        self.log.emit("TU download completed.")
        self.finished.emit(stats)

    def _progress_callback(self, completed, total):
        if total > 0:
            self.progress.emit(completed, total)

    def _safe_name(self, name):
        import re
        name = re.sub(r'[<>:"/\\|?*]', "_", name)
        return name[:100].strip()

class XboxTUMApp(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Xbox 360 TU Manager")
        self.resize(1100, 700)

        self.token = None
        self.api_key = None
        self.juegos = []

        self._build_ui()
        self.load_saved_config()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)

        # ================= LOGIN =================
        top = QHBoxLayout()

        login_box = QGroupBox("Login XboxUnity / API Key")
        login_layout = QVBoxLayout()

        self.entry_user = QLineEdit()
        self.entry_pass = QLineEdit()
        self.entry_pass.setEchoMode(QLineEdit.Password)
        self.entry_apikey = QLineEdit()

        login_layout.addWidget(QLabel("Username"))
        login_layout.addWidget(self.entry_user)
        login_layout.addWidget(QLabel("Password"))
        login_layout.addWidget(self.entry_pass)
        login_layout.addWidget(QLabel("API Key"))
        login_layout.addWidget(self.entry_apikey)

        self.login_btn = QPushButton("Login")
        self.login_btn.clicked.connect(self.login)
        login_layout.addWidget(self.login_btn)

        login_box.setLayout(login_layout)

        top.addWidget(login_box)

        layout.addLayout(top)

        # ================= GAME TABLE =================
        self.tree = QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(["Game", "MediaID", "TitleID"])
        layout.addWidget(self.tree)

        # ================= ACTION BUTTONS =================
        btn_row = QHBoxLayout()

        self.btn_folder = QPushButton("Select Games Folder")
        self.btn_folder.clicked.connect(self.select_folder)

        self.btn_tu = QPushButton("Search & Download TUs")
        self.btn_tu.clicked.connect(self.search_and_download_tus)

        btn_row.addWidget(self.btn_folder)
        btn_row.addWidget(self.btn_tu)

        layout.addLayout(btn_row)

        # ================= PROGRESS =================
        self.progress = QProgressBar()
        layout.addWidget(self.progress)

        # ================= LOG =================
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log)

    # ================= CORE HELPERS =================

    def _log(self, msg):
        self.log.append(msg)

    def _msg(self, title, msg):
        QMessageBox.information(self, title, msg)

    def _err(self, title, msg):
        QMessageBox.critical(self, title, msg)

    # ================= PLACEHOLDER METHODS =================
    # (we will port logic next step-by-step)

    def load_saved_config(self):
        config = load_config()

        self.entry_user.setText(config.get("username", ""))
        self.entry_pass.setText(config.get("password", ""))
        self.entry_apikey.setText(config.get("api_key", ""))

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
            self._log("API Key saved.")

            # optional connectivity check
            try:
                if probar_conectividad():
                    self._log("XboxUnity connectivity OK.")
                else:
                    self._log("WARNING: XboxUnity connectivity issue.")
            except Exception as e:
                self._log(f"Connectivity error: {e}")

            return

        # Username/password login
        if not username or not password:
            self._err("Login Error", "Enter username/password or API key")
            return

        self._log("Checking XboxUnity...")

        try:
            if not probar_conectividad():
                self._err("Error", "Cannot reach XboxUnity")
                return
        except Exception as e:
            self._err("Error", str(e))
            return

        self._log("Logging in...")

        token = login_xboxunity(username, password)

        if token:
            self.token = token
            self.api_key = None

            config["username"] = username
            config["password"] = password
            config.pop("api_key", None)

            save_config(config)

            self._log("Login successful.")
        else:
            self._err("Login Failed", "Invalid credentials")
    def test_ftp_connection(self):
        self._log("FTP test clicked (to be implemented)")

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Games Folder")
        if folder:
            self._log(f"Selected: {folder}")

    def search_and_download_tus(self):
        if not self.games:
            self._err("Error", "No games loaded")
            return
        folder = QFileDialog.getExistingDirectory(self, "Select output folder")
        if not folder:
            return
        self.worker = TUDownloadWorker(
            games=self.games,
            token=self.token,
            api_key=self.api_key,
            output_folder=folder
        )
        self.worker.log.connect(self._log)
        self.worker.progress.connect(self.update_file_progress)
        self.worker.game_progress.connect(self.update_game_progress)
        self.worker.finished.connect(self.download_finished)

        self.worker.start()

    def update_file_progress(self, done, total):
        if total > 0:
            self.progress.setMaximum(total)
            self.progress.setValue(done)


    def update_game_progress(self, current, total):
        self._log(f"Game progress: {current}/{total}")

    def download_finished(self, stats):
        self._log("\n=== SUMMARY ===")
        self._log(f"Games: {stats['games_total']}")
        self._log(f"With TUs: {stats['games_with_tu']}")
        self._log(f"Downloaded: {stats['tus_downloaded']}")
        self._log(f"Errors: {stats['errors']}")

        self._msg("Done", "TU download completed")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = XboxTUMApp()
    window.show()
    sys.exit(app.exec())