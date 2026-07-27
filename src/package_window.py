import json
import shutil
import subprocess

import sys

from config import get_app_dir
from pathlib import Path
import xml.etree.ElementTree as ET

from line_profiler_pycharm import profile
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QRect, QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QWidget,
    QPushButton,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QFormLayout,
    QGroupBox,
    QHeaderView, QApplication, QMessageBox, QSizePolicy, QFrame, QGraphicsDropShadowEffect,
)

def read_bytes(file_path: Path):
    with open(file_path, "rb") as f:
        from pathlib import Path

        data = Path(file_path).read_bytes()

        for word in [b"XNA", b"Xbox", b"default.xex", b"Content"]:
            if word in data:
                print("Found:", word.decode())

def move_folders_to_type(root):
    root = Path(root)

    mapping = {
        "(XBLIG)": "XBLIG",
        "(DLC)": "DLC",
        "(Addon)": "ADDON",
        "(XBLA)": "XBLA",
        "(GOD)": "GOD",
    }

    ignore = set(mapping.values())

    # Only scan game folders, not Xbox internal folders
    folders = sorted(
        [p for p in root.iterdir() if p.is_dir()],
        key=lambda x: len(x.parts),
        reverse=True
    )

    for folder in folders:

        print(f"Checking {folder}")

        if folder.name in ignore:
            continue

        category = None

        for marker, cat in mapping.items():
            if marker in folder.name:
                category = cat
                break

        # unknown folders become DLC
        if category is None:
            category = "DLC"

        dest_dir = root / category
        dest_dir.mkdir(exist_ok=True)

        dest = dest_dir / folder.name

        if folder == dest:
            continue

        if dest.exists():
            print(f"Already exists: {dest}")
            continue

        print(f"Moving {folder} -> {dest}")
        shutil.move(str(folder), str(dest))

from pathlib import Path
import subprocess

ILSPY_CMD = get_app_dir() / "assets" / "tools" / "ILSpy" / "ILSpyCmd.exe"
ILSPY_GUI = get_app_dir() / "assets"/ "tools" / "ILSpy" / "ILSpy.exe"

import os

def open_solution(project_dir: Path):
    for csproj in project_dir.glob("*.csproj"):
        os.startfile(csproj)
        return


def decompile_project(exe: Path):
    output_dir = exe.parent / "decompiled"
    output_dir.mkdir(exist_ok=True)

    subprocess.run(
        [
            str(ILSPY_CMD),
            str(exe),
            "--project",
            "-o",
            str(output_dir),
        ],
        check=True,
    )

    return output_dir

def cleanup_nested_categories(root):
    root = Path(root)

    categories = {
        "XBLIG",
        "DLC",
        "ADDON",
        "XBLA",
    }

    for category in categories:
        category_path = root / category

        if not category_path.exists():
            continue

        print(f"\nChecking {category_path}")

        # Find repeated category folders
        for nested in sorted(
            category_path.rglob(category),
            key=lambda p: len(p.parts),
            reverse=True
        ):
            if nested == category_path:
                continue

            print(f"Found nested folder: {nested}")

            parent = nested.parent

            # Move everything inside nested up one level
            for item in nested.iterdir():

                destination = parent / item.name

                if destination.exists():
                    print(f"Skipping existing: {destination}")
                    continue

                print(f"Moving {item} -> {destination}")
                shutil.move(str(item), str(destination))

            # remove empty folder
            try:
                nested.rmdir()
                print(f"Removed empty folder: {nested}")
            except OSError:
                pass

import io
import io

class QtLogger(io.TextIOBase):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback
        self._buffer = ""

    def write(self, text):
        self._buffer += text

        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if line:
                self.callback(line)

        return len(text)

    def flush(self):
        if self._buffer:
            self.callback(self._buffer)
            self._buffer = ""

    def reconfigure(self, **kwargs):
        # ignore stdout reconfigure calls
        pass

    @property
    def encoding(self):
        return "utf-8"

import json


def get_folder_mtime(path):
    return max((p.stat().st_mtime for p in path.rglob("*")), default=0)

def save_cache(games):
    cache_file = get_app_dir() / "cache" / "xblig_games.json"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    root = get_app_dir() / "downloads" / "XBLIG"
    data = {
        "mtime": get_folder_mtime(root),
        "games": games,
    }

    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False, default=str)

def load_cache():
    cache_file = get_app_dir() / "cache" / "xblig_games.json"
    if not cache_file.exists():
        return None

    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Failed to load cache: {e}")
        return None

class ClickOverlay(QWidget):
    def __init__(self, launcher):
        super().__init__(launcher)
        self.launcher = launcher

    def mousePressEvent(self, event):
        self.launcher.hide_settings_drawer()

class XBLIG_Dialog(QDialog):

    def find_xblig_packages(self, root: str | Path, log=None):

        root = Path(root)
        games = []

        STFS_MAGIC = {
            b"CON ",
            b"LIVE",
            b"PIRS",
        }

        def is_stfs(path: Path):
            try:
                with path.open("rb") as f:
                    return f.read(4) in STFS_MAGIC
            except Exception:
                return False

        def parse_xml(xml_file: Path):

            data = {}

            if not xml_file.exists():
                return data

            try:
                tree = ET.parse(xml_file)
                root_xml = tree.getroot()

                title_info = root_xml.find(".//TitleInfo")

                if title_info is not None:
                    data["title"] = title_info.attrib.get("Name")
                    data["virtual_title_id"] = title_info.attrib.get(
                        "VirtualTitleID"
                    )
                    data["xml_title_id"] = title_info.attrib.get(
                        "TitleID"
                    )
                    data["image_path"] = title_info.attrib.get(
                        "ImagePath"
                    )

            except Exception as e:
                print(f"XML error {xml_file}: {e}")

            return data

        # scan game folders first
        for game_folder in root.iterdir():

            if not game_folder.is_dir():
                continue
            if log: log(f"Checking Folder {game_folder}")
            folder_title = game_folder.name

            packages = []

            # find STFS packages inside this game folder
            for package in game_folder.rglob("*"):

                if package.is_file() and is_stfs(package):
                    packages.append(package)

            if not packages:
                continue

            for package in packages:

                title_id = None
                content_type = None

                try:
                    content_type = package.parent.name
                    title_id = package.parent.parent.name
                except:
                    pass

                extracted = package.parent / "extracted"

                game_info = (
                        extracted / "GameInfo.xml"
                )

                xml_data = parse_xml(game_info)

                # title priority
                title = (
                        xml_data.get("title")
                        or folder_title
                        or package.stem
                )

                exe_file = None

                if extracted.exists():
                    for exe in extracted.rglob("*.exe"):
                        exe_file = exe
                        break

                games.append({

                    "title": title,

                    "folder_title": folder_title,

                    "title_id": title_id,

                    "content_type": content_type,

                    "content_name":
                        "Xbox Live Indie Game",

                    "package": package,

                    "extracted": (
                        extracted
                        if extracted.exists()
                        else None
                    ),

                    "game_root": (
                        extracted
                        if extracted.exists()
                        else package.parent
                    ),

                    "exe": (
                        exe_file
                        if isinstance(exe_file, Path) and exe_file.exists()
                        else None
                    ),

                    "xml": (
                        game_info
                        if game_info.exists()
                        else None
                    ),

                    **xml_data
                })
        self.log_message(f"Scanner Found {len(games)} XBLIG Games")
        return games

    def resizeEvent(self, event):
        super().resizeEvent(event)

        if hasattr(self, "settings_drawer"):
            self.settings_drawer.setGeometry(
                self.width() - self.settings_drawer.width(),
                0,
                self.settings_drawer.width(),
                self.height()
            )

        if hasattr(self, "overlay"):
            self.overlay.setGeometry(
                0,
                0,
                self.width(),
                self.height()
            )

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

    def __init__(self, parent=None):
        super().__init__(parent)
        self.drawer_open = False
        self._last_mtime = None
        self._cache = None
        self.close_btn = None
        self.games = []
        self.setWindowTitle("XBLIG Emulator")
        self.resize(1100, 750)

        self.build_ui()
        self.create_settings_drawer()
        self.apply_style()

    def print_games(self):
        for i, game in enumerate(self.games, 1):
            print("=" * 80)
            print(f"Game #{i}")
            print("=" * 80)

            for key, value in game.items():
                label = key.replace("_", " ").title()
                print(f"{label:<15}: {value}")

            print()

    from pathlib import Path
    def get_selected_game(self):
        indexes = self.game_table.selectionModel().selectedRows()

        if not indexes:
            return None

        row = indexes[0].row()

        return self.games[row]


    def decompile_selected(self):
        game = self.get_selected_game()

        exe = game.get("exe")
        if not exe:
            QMessageBox.warning(self, "No Executable",
                                "Extract the game first.")
            return

        exe = Path(exe)

        self.log_message(f"Generating Visual Studio project for {exe.name}...")

        try:
            project_dir = decompile_project(exe)
        except subprocess.CalledProcessError as e:
            QMessageBox.critical(self, "ILSpy", str(e))
            return

        self.log_message("Visual Studio project created.")

        subprocess.Popen(["explorer", str(project_dir)])

    from PySide6.QtCore import QObject, QThread, Signal

    class ScanWorker(QObject):

        finished = Signal(list)
        log = Signal(str)

        def __init__(self, root, scan_func, force=False):
            super().__init__()
            self.root = root
            self.force = force
            self.scan_func = scan_func

        def run(self):

            try:
                self.log.emit("Checking game cache...")

                current_mtime = get_folder_mtime(self.root)
                cache = None if self.force else load_cache()

                if cache and cache.get("mtime") == current_mtime:
                    games = cache["games"]
                    for game in games:
                        for key in [
                            "package",
                            "extracted",
                            "game_root",
                            "exe",
                            "xml"
                        ]:
                            if game.get(key):
                                game[key] = Path(game[key])
                    self.log.emit(
                        f"Loaded {len(games)} games from cache."
                    )

                else:
                    self.log.emit("Scanning folders...")

                    games = self.scan_func(self.root, self.log.emit)

                    save_cache(games)

                    self.log.emit("Cache updated.")

                self.finished.emit(games)

            except Exception as e:
                self.log.emit(f"Scanner error: {e}")
                self.finished.emit([])

    def rescan_games_responsive(self, force=False):
        root = get_app_dir() / "downloads" / "XBLIG"
        self.scan_btn.setEnabled(False)

        self.thread = QThread(self)
        self.worker = self.ScanWorker(root,self.find_xblig_packages, force)

        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)

        self.worker.log.connect(self.log_message)
        self.worker.finished.connect(self.scan_finished)

        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)

        self.thread.start()

    def scan_finished(self, games):
        self.games = games
        self.load_games(self.games)
        self.log_message(f"Loaded {len(self.games)} games.")
        self.scan_btn.setEnabled(True)

    # def rescan_games(self, force=False):
    #     self.log_message("Checking game cache...")
    #     root = get_app_dir() / "downloads" / "XBLIG"
    #     current_mtime = get_folder_mtime(root)
    #
    #     cache = None if force else load_cache()
    #
    #     if cache and cache.get("mtime") == current_mtime:
    #         self.games = cache["games"]
    #         self.log_message(f"Loaded {len(self.games)} games from cache.")
    #     else:
    #         self.log_message("Scanning folders...")
    #         self.games = self.find_xblig_packages(ROOT)
    #         save_cache(self.games)
    #         self.log_message("Cache updated.")
    #
    #     self.load_games(self.games)
    #     self.log_message(f"Loaded {len(self.games)} games.")

    def game_selected(self):

        row = self.game_table.currentRow()

        if row < 0:
            return

        game = self.games[row]

        root = get_app_dir() / "downloads"


        self.title_lbl.setText(game["title"])
        self.titleid_lbl.setText(
            str(game.get("title_id") or "-")
        )
        self.virtualid_lbl.setText(
            game.get("virtual_title_id", "")
        )
        if game.get("exe"):
            relative_path = Path(str(game["exe"])).relative_to(root.parent)
            self.exe_lbl.setText(str(relative_path))
        else:
            self.exe_lbl.setText("-")
        if game.get("xml"):
            relative_path = Path(str(game["xml"])).relative_to(root.parent)
            self.xml_lbl.setText(str(relative_path))
        else:
            self.xml_lbl.setText("-")

        if not self.drawer_open:
            self.show_settings_drawer()

    def extract_missing(self):
        self.log_message(f"\nFound {len(self.games)} Xbox Live Indie Games\n")
        for i, game in enumerate(self.games, 1):

            # Auto extract missing games
            if game.get("extracted") is None and game.get("package"):
                extracted = self.extract_xblig_package(game)

                if extracted:
                    game["extracted"] = str(extracted)
            else:
                self.log_message(f"Skipping {game.get("title")}")

    def log_message(self, message):
        self.log_window.append(message)

    def extract_xblig_package(self, game):
        package = game.get("package")

        if not package:
            return None

        package = Path(package)

        if not package.exists():
            print(f"Package missing: {package}")
            return None

        self.log_message(f"Extracting: {package}")

        from stfs_extract import extract_live_pirs

        # Create extracted folder beside package
        extracted_path = package.parent / "extracted"

        extracted_path.mkdir(parents=True, exist_ok=True)

        try:
            from contextlib import redirect_stdout

            with redirect_stdout(QtLogger(self.log_message)):
                extract_live_pirs(package, extracted_path)

            print(f"Extracted to: {extracted_path}")

        except Exception as e:
            print(f"Extraction failed: {e}")
            return None

        return extracted_path

    def load_games(self, games):
        self.game_table.setRowCount(0)

        for game in games:
            row = self.game_table.rowCount()
            self.game_table.insertRow(row)

            ready = (
                    game["exe"] is not None
                    and game["xml"] is not None
            )

            status = "Ready" if ready else "Needs Build"

            self.game_table.setItem(row, 0, QTableWidgetItem(game["title"]))
            self.game_table.setItem(row, 1, QTableWidgetItem(status))
            self.game_table.setItem(row, 2, QTableWidgetItem(
                "Yes" if game["extracted"] else "No"))
            self.game_table.setItem(row, 3, QTableWidgetItem(
                Path(game["exe"]).name if game["exe"] else ""))

    def build_selected(self):
        self.log_message("Building selected game...")
        self.decompile_selected()

    def launch_selected(self):
        self.log_message("Launching selected game...")

    def refresh_games(self):
        self.load_games(self.games)

    def open_selected_folder(self):
        self.log_message("Opening game folder...")

    from PySide6.QtCore import QRect, QPropertyAnimation, QEasingCurve

    def show_settings_drawer(self):
        self.drawer_open = True
        self.settings_drawer.show()

        self.overlay.show()
        self.overlay.raise_()
        self.settings_drawer.raise_()

        w = self.settings_drawer.width()

        self.anim = QPropertyAnimation(self.settings_drawer, b"geometry")
        self.anim.setDuration(250)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.anim.setStartValue(
            QRect(self.width(), 0, w, self.height())
        )
        self.anim.setEndValue(
            QRect(self.width() - w, 0, w, self.height())
        )

        self.anim.start()

    def hide_settings_drawer(self):
        self.drawer_open = False
        w = self.settings_drawer.width()

        self.anim = QPropertyAnimation(self.settings_drawer, b"geometry")
        self.anim.setDuration(250)
        self.anim.setEasingCurve(QEasingCurve.Type.InCubic)

        self.anim.setStartValue(
            QRect(self.width() - w, 0, w, self.height())
        )
        self.anim.setEndValue(
            QRect(self.width(), 0, w, self.height())
        )

        self.anim.finished.connect(self.overlay.hide)
        self.anim.start()

    def create_settings_drawer(self):

        self.overlay = ClickOverlay(self)
        self.overlay.setStyleSheet("background-color: rgba(0,0,0,120);")
        self.overlay.hide()

        self.settings_drawer = QFrame(self)
        self.settings_drawer.setObjectName("settingsDrawer")
        self.settings_drawer.setFixedWidth(750)

        drawer_layout = QVBoxLayout(self.settings_drawer)
        drawer_layout.setContentsMargins(20, 20, 20, 20)
        drawer_layout.setSpacing(15)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(40)
        shadow.setOffset(-5, 0)
        self.settings_drawer.setGraphicsEffect(shadow)

        header = QHBoxLayout()

        title = QLabel("Game Details")
        title.setStyleSheet("font-size:16px;font-weight:bold")

        close = QPushButton("✕")
        close.clicked.connect(self.hide_settings_drawer)

        header.addWidget(title)
        header.addStretch()
        header.addWidget(close)

        drawer_layout.addLayout(header)

        # Game Information

        info_group = QGroupBox("Game Information")
        info_group.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Maximum
        )
        form = QFormLayout(info_group)
        form.setContentsMargins(8, 8, 8, 8)
        form.setVerticalSpacing(4)

        self.title_lbl = QLabel("-")
        self.titleid_lbl = QLabel("-")
        self.virtualid_lbl = QLabel("-")
        self.exe_lbl = QLabel("-")
        self.xml_lbl = QLabel("-")
        self.status_lbl = QLabel("-")

        form.addRow("Title", self.title_lbl)
        form.addRow("Title ID", self.titleid_lbl)
        form.addRow("Virtual ID", self.virtualid_lbl)
        form.addRow("Executable", self.exe_lbl)
        form.addRow("GameInfo.xml", self.xml_lbl)
        form.addRow("Status", self.status_lbl)

        drawer_layout.addWidget(info_group)

        action_group = QGroupBox("Actions")
        action_group.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Maximum
        )
        actions = QHBoxLayout(action_group)
        actions.setContentsMargins(8, 8, 8, 8)
        self.run_btn = QPushButton("Launch Game")
        self.validate_btn = QPushButton("Validate")
        self.open_folder_btn = QPushButton("Open Folder")
        self.open_xml_btn = QPushButton("Open XML")
        self.export_btn = QPushButton("Export JSON")

        actions.addWidget(self.run_btn)
        actions.addWidget(self.validate_btn)
        actions.addWidget(self.open_folder_btn)
        actions.addWidget(self.open_xml_btn)
        actions.addWidget(self.export_btn)
        actions.addStretch()
        #
        # right_layout.addWidget(action_group, 0)
        # right_layout.addStretch(1)
        #
        # splitter.addWidget(left)
        # splitter.addWidget(right)
        #
        # splitter.setStretchFactor(0, 3)
        # splitter.setStretchFactor(1, 1)
        #
        # splitter.addWidget(left)
        # main_layout.addWidget(splitter)

        drawer_layout.addWidget(action_group)
        drawer_layout.addStretch()
        self.settings_drawer.hide()

    def build_ui(self):

        main_layout = QVBoxLayout(self)

        #
        # Toolbar
        #

        toolbar = QHBoxLayout()
        self.scan_btn = QPushButton("Scan Games")
        self.scan_btn.clicked.connect(self.rescan_games_responsive)

        self.extract_btn = QPushButton("Extract Missing")
        self.extract_btn.clicked.connect(self.extract_missing)

        self.build_btn = QPushButton("Build Game")
        self.build_btn.clicked.connect(self.build_selected)

        self.launch_btn = QPushButton("Launch")
        self.launch_btn.clicked.connect(self.launch_selected)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_games)

        self.open_folder_btn = QPushButton("Open Folder")
        self.open_folder_btn.clicked.connect(self.open_selected_folder)

        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.close)

        toolbar.addWidget(self.scan_btn)
        toolbar.addWidget(self.extract_btn)
        toolbar.addWidget(self.build_btn)
        toolbar.addWidget(self.launch_btn)
        toolbar.addWidget(self.refresh_btn)
        toolbar.addWidget(self.open_folder_btn)
        toolbar.addWidget(self.close_btn)
        toolbar.addStretch()

        main_layout.addLayout(toolbar)

        #
        # Splitter
        #

        splitter = QSplitter(Qt.Orientation.Horizontal)

        ###########################################################
        # LEFT SIDE
        ###########################################################

        left = QWidget()
        left_layout = QVBoxLayout(left)

        left = QWidget()
        left_layout = QVBoxLayout(left)

        # Splitter so table gets most of the space
        left_splitter = QSplitter(Qt.Orientation.Vertical)

        #
        # Game Table
        #

        self.game_table = QTableWidget(0, 4)

        self.game_table.setHorizontalHeaderLabels([
            "Title",
            "Status",
            "Extracted",
            "Executable",
        ])

        header = self.game_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        self.game_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.game_table.setSelectionMode(QTableWidget.SingleSelection)
        self.game_table.setEditTriggers(QTableWidget.NoEditTriggers)

        self.game_table.itemSelectionChanged.connect(self.game_selected)

        left_splitter.addWidget(self.game_table)

        #
        # Log Window
        #

        log_group = QGroupBox("Log")
        log_layout = QVBoxLayout(log_group)

        self.log_window = QTextEdit()
        self.log_window.setReadOnly(True)

        log_layout.addWidget(self.log_window)

        left_splitter.addWidget(log_group)

        # Table gets ~80%, log gets ~20%
        left_splitter.setStretchFactor(0, 5)
        left_splitter.setStretchFactor(1, 1)

        left_layout.addWidget(left_splitter)

        splitter.addWidget(left)

        splitter.setStretchFactor(0, 1)

        main_layout.addWidget(splitter)

        self.game_table.selectRow(0)

    def add_demo_game(self, title, status, extracted, exe):

        row = self.game_table.rowCount()

        self.game_table.insertRow(row)

        self.game_table.setItem(row, 0, QTableWidgetItem(title))
        self.game_table.setItem(row, 1, QTableWidgetItem(status))
        self.game_table.setItem(row, 2, QTableWidgetItem(extracted))
        self.game_table.setItem(row, 3, QTableWidgetItem(exe))

if __name__ == "__main__":

    app = QApplication(sys.argv)
    xbdlg = XBLIG_Dialog()
    xbdlg.exec()

    cleanup_nested_categories(r"C:\PycharmProjects\xenia-game-manager\src\downloads")

    move_folders_to_type(get_app_dir() / "downloads")
    #
    # exe = Path(get_app_dir() / "downloads" / "XBLIG" / "Alien Jelly (World) (XBLIG)/584E07D2/00000002/62F2648203AAB1C526B538091DF3BBE8CFC6E7E758_extracted/584E07D1/Game.exe")
    # if exe.exists(): read_bytes(exe)
