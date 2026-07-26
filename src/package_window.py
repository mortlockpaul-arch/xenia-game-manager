import json
import shutil
import subprocess

import sys

from config import get_app_dir
from pathlib import Path
import xml.etree.ElementTree as ET

from PySide6.QtCore import Qt
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
    QHeaderView, QApplication, QMessageBox,
)

def find_xblig_packages(root: str | Path):

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


    return games

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

CACHE_FILE = get_app_dir() / "cache" / "xblig_games.json"
ROOT = get_app_dir() / "downloads" / "XBLIG"


def get_folder_mtime(path):
    return max((p.stat().st_mtime for p in path.rglob("*")), default=0)


def save_cache(games):
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "mtime": get_folder_mtime(ROOT),
        "games": games,
    }

    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False, default=str)


def load_cache():
    if not CACHE_FILE.exists():
        return None

    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Failed to load cache: {e}")
        return None

class XBLIG_Dialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)

        self._last_mtime = None
        self._cache = None
        self.close_btn = None
        self.games = []
        self.setWindowTitle("XBLIG Emulator")
        self.resize(1100, 750)
        self.build_ui()
        self.rescan_games()

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

        self.log.append(f"Generating Visual Studio project for {exe.name}...")

        try:
            project_dir = decompile_project(exe)
        except subprocess.CalledProcessError as e:
            QMessageBox.critical(self, "ILSpy", str(e))
            return

        self.log.append("Visual Studio project created.")

        subprocess.Popen(["explorer", str(project_dir)])


    def rescan_games(self, force=False):
        self.log.append("Checking game cache...")

        current_mtime = get_folder_mtime(ROOT)

        cache = None if force else load_cache()

        if (
                cache
                and cache.get("mtime") == current_mtime
        ):
            self.games = cache["games"]
            self.log.append(f"Loaded {len(self.games)} games from cache.")
        else:
            self.log.append("Scanning folders...")
            self.games = find_xblig_packages(ROOT)
            save_cache(self.games)
            self.log.append("Cache updated.")

        self.load_games(self.games)
        self.log.append(f"Found {len(self.games)} games.")

    def game_selected(self):

        row = self.game_table.currentRow()

        if row < 0:
            return

        game = self.games[row]

        self.title_lbl.setText(game["title"])
        self.titleid_lbl.setText(game["title_id"])
        self.virtualid_lbl.setText(
            game.get("virtual_title_id", "")
        )
        self.exe_lbl.setText(str(game["exe"]))
        self.xml_lbl.setText(str(game["xml"]))

    def extract_missing(self):
        self.log.append(f"\nFound {len(self.games)} Xbox Live Indie Games\n")
        for i, game in enumerate(self.games, 1):

            # Auto extract missing games
            if game.get("extracted") is None and game.get("package"):
                extracted = self.extract_xblig_package(game)

                if extracted:
                    game["extracted"] = str(extracted)
            else:
                self.log.append(f"Skipping {game.get("title")}")

    def log_message(self, message):
        self.log.append(message)

    def extract_xblig_package(self, game):
        package = game.get("package")

        if not package:
            return None

        package = Path(package)

        if not package.exists():
            print(f"Package missing: {package}")
            return None

        self.log.append(f"Extracting: {package}")

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
        self.log.append("Building selected game...")
        self.decompile_selected()

    def launch_selected(self):
        self.log.append("Launching selected game...")

    def refresh_games(self):
        self.load_games(self.games)

    def open_selected_folder(self):
        self.log.append("Opening game folder...")

    def build_ui(self):

        main_layout = QVBoxLayout(self)

        #
        # Toolbar
        #

        toolbar = QHBoxLayout()
        self.scan_btn = QPushButton("Scan Games")
        self.scan_btn.clicked.connect(self.rescan_games)

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

        toolbar.addWidget(self.scan_btn)
        toolbar.addWidget(self.extract_btn)
        toolbar.addWidget(self.build_btn)
        toolbar.addWidget(self.launch_btn)
        toolbar.addWidget(self.refresh_btn)
        toolbar.addWidget(self.open_folder_btn)
        toolbar.addStretch()

        main_layout.addLayout(toolbar)

        #
        # Splitter
        #

        splitter = QSplitter(Qt.Horizontal)

        ###########################################################
        # LEFT SIDE
        ###########################################################

        left = QWidget()
        left_layout = QVBoxLayout(left)

        self.game_table = QTableWidget(0, 4)

        self.game_table.setHorizontalHeaderLabels(
            [
                "Title",
                "Status",
                "Extracted",
                "Executable",
            ]
        )

        header = self.game_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)

        self.game_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.game_table.setSelectionMode(QTableWidget.SingleSelection)
        self.game_table.setEditTriggers(QTableWidget.NoEditTriggers)

        left_layout.addWidget(self.game_table)
        self.game_table.itemSelectionChanged.connect(
            self.game_selected
        )
        ###########################################################
        # RIGHT SIDE
        ###########################################################

        right = QWidget()
        right_layout = QVBoxLayout(right)

        #
        # Game Information
        #

        info_group = QGroupBox("Game Information")

        form = QFormLayout(info_group)

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

        right_layout.addWidget(info_group)

        #
        # Actions
        #

        action_group = QGroupBox("Actions")

        actions = QVBoxLayout(action_group)

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

        right_layout.addWidget(action_group)

        splitter.addWidget(left)
        splitter.addWidget(right)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        main_layout.addWidget(splitter)

        #
        # Log Window
        #

        log_group = QGroupBox("Log")

        log_layout = QVBoxLayout(log_group)

        self.log = QTextEdit()
        self.log.setReadOnly(True)

        log_layout.addWidget(self.log)

        main_layout.addWidget(log_group)

        #
        # Bottom Buttons
        #

        bottom = QHBoxLayout()

        bottom.addStretch()

        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.close)

        bottom.addWidget(self.close_btn)

        main_layout.addLayout(bottom)

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
