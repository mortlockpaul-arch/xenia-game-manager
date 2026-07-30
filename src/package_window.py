import json
import logging
import random
import shutil
import subprocess
from xml.etree import ElementTree as ET

import time
from dataclasses import dataclass, asdict
from typing import cast

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
    QHeaderView, QApplication, QMessageBox, QSizePolicy, QFrame, QGraphicsDropShadowEffect, QCheckBox,
)

from convert_xna_projects import FNA_VERSION

def convert_xnb_folder_alba(game:XBLIGGame):
    if game.extracted is None:
        print(f"Game not extracted: {game}")
        return None
    folder = game.extracted
    content_dir = folder / "584E07D1" / "Content"
    # copy_content_folder(content_dir)
    output_dir = content_dir.parent / "Content_Output"
    if not content_dir.exists():
        print(f"No Content folder found: {content_dir}")

    content_dir = Path(content_dir)
    output_dir = Path(output_dir)
    print("content_dir:", content_dir)
    print("output_dir:", output_dir)

    alba = Path(get_app_dir() / "assets/tools/xnb_conversion/Alba.XnaConvert.0.1.2/Alba.XnaConvert.exe")

    failed = []
    #
    # for xnb_file in content_dir.rglob("*.xnb"):
    #     relative = xnb_file.relative_to(content_dir)
    #     out_file = output_dir / relative
    #     out_file.parent.mkdir(parents=True, exist_ok=True)
    # print("xnb_file:", xnb_file)
    # print("out_file:", out_file)
    # print(f"Converting: {xnb_file}")

    try:
        result = subprocess.run(
            [
                str(alba),
                "convert",
                "-v", "4",
                "-d", str(content_dir),
                "-o", str(output_dir),
                "-r"
            ],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            print(f"FAILED: {content_dir}")
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)
            failed.append(content_dir)
        else:
            print("OK")
            if result.stdout.strip():
                print(result.stdout)

    except Exception as e:
        print(f"ERROR running ALBA on {content_dir}")
        print(e)
        failed.append(content_dir)

    print("\n===================")
    print("Conversion complete")
    print(f"Failed files: {len(failed)}")

    if failed:
        print("\nFailed XNB files:")
        for f in failed:
            print(f)

    return failed


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


import os

def open_solution(project_dir: Path):
    for csproj in project_dir.glob("*.csproj"):
        os.startfile(csproj)
        return


def decompile_project(exe: Path):
    output_dir = exe.parent.parent.parent / "decompiled"
    output_dir.mkdir(exist_ok=True)
    ilspy_cmd = get_app_dir() / "assets" / "tools" / "ILSpy" / "ILSpyCmd.exe"
    ilspy_gui = get_app_dir() / "assets" / "tools" / "ILSpy" / "ILSpy.exe"

    subprocess.run(
        [
            str(ilspy_cmd),
            str(exe),
            "-p",
            "-o",str(output_dir),
            "-l","latest"
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
        "games": [
            game.to_dict()
            for game in games
        ],
    }

    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            indent=4,
            ensure_ascii=False
        )

def load_cache():
    cache_file = get_app_dir() / "cache" / "xblig_games.json"

    if not cache_file.exists():
        return None

    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        data["games"] = [
            XBLIGGame.from_dict(game)
            for game in data.get("games", [])
        ]

        return data

    except Exception as e:
        print(f"Failed to load cache: {e}")
        return None

class ClickOverlay(QWidget):
    def __init__(self, launcher):
        super().__init__(launcher)
        self.launcher = launcher

    def mousePressEvent(self, event):
        self.launcher.hide_settings_drawer()
from dataclasses import dataclass, fields
from pathlib import Path


@dataclass
class XBLIGGame:
    title: str
    folder_title: str | None = None
    title_id: str | None = None
    virtual_title_id: str | None = None
    xml_title_id: str | None = None

    content_type: str | None = None
    content_name: str | None = None
    content_converted: str = "No"
    content_format: str = "xnb content"

    package: Path | None = None
    extracted: Path | None = None
    game_root: Path | None = None

    exe: Path | None = None
    xml: Path | None = None
    decompiled: Path | None = None

    # def __init__(self):

    def __post_init__(self):
        for field in (
                "package",
                "extracted",
                "game_root",
                "exe",
                "xml",
                "decompiled",
        ):
            value = getattr(self, field)
            if isinstance(value, str):
                setattr(self, field, Path(value))

    def to_dict(self):
        data = {}

        for field in fields(self):
            value = getattr(self, field.name)

            if isinstance(value, Path):
                value = str(value)

            data[field.name] = value

        return data


    @classmethod
    def from_dict(cls, data):
        path_fields = {
            "package",
            "extracted",
            "game_root",
            "exe",
            "xml",
            "decompiled",
        }

        converted = {}

        for field in fields(cls):
            value = data.get(field.name)

            if field.name in path_fields and value:
                value = Path(value)

            converted[field.name] = value

        return cls(**converted)


def copy_content_folder(folder, dest):
    source = folder
    # destination = folder.parent / "content_backup"
    # if destination.exists() and destination.is_dir():
    #     shutil.rmtree(destination)
    shutil.copytree(folder, dest)


class ConvertXnaProjects:

    def __init__(self, project_path, log, games):
        self.project_path = Path(project_path)
        self.log = log
        self.log_signal = Signal(log, str)
        self.games = games

    def log_message(self, message):
        self.log(message)

    def convert_xblig_to_fna(self, project_path):
        """
        Convert an ILSpy decompiled XBLIG XNA project to an FNA project.

        - Changes target framework
        - Removes XNA references
        - Adds FNA NuGet package
        - Keeps local DLL references
        - Backs up original csproj
        # """
        # project_base = get_app_dir() / "downloads"
        # self.log_message(f"Converting base {project_base} XBLIG to FNA")
        project_path = Path(project_path)
        self.log_message(f"Converting project {project_path} XBLIG to FNA")
        if not project_path.exists():
            raise FileNotFoundError(project_path)

        if project_path.suffix.lower() != ".csproj":
            raise ValueError("Expected .csproj file")

        print(f"Converting: {project_path.name}")

        backup = project_path.with_suffix(".xna.csproj")

        if not backup.exists():
            shutil.copy(project_path, backup)
            print(f"Backup created: {backup.name}")

        tree = ET.parse(project_path)
        root = tree.getroot()

        # MSBuild namespace handling
        ns = ""

        if root.tag.startswith("{"):
            ns = root.tag.split("}")[0] + "}"

        def tag(name):
            return f"{ns}{name}"

        # -------------------------------------------------
        # Fix Target Framework
        # -------------------------------------------------

        for propgroup in root.findall(tag("PropertyGroup")):

            target = propgroup.find(tag("TargetFramework"))

            if target is not None:
                print("  Updating framework")
                target.text = "net8.0-windows"

            lang = propgroup.find(tag("LangVersion"))

            if lang is not None:
                lang.text = "latest"

        # -------------------------------------------------
        # Remove XNA Referencesx
        # -------------------------------------------------

        xna_names = [
            "Microsoft.Xna.Framework",
            "Microsoft.Xna.Framework.Game",
            "Microsoft.Xna.Framework.Graphics",
            "Microsoft.Xna.Framework.Audio",
            "Microsoft.Xna.Framework.Net",
            "Microsoft.Xna.Framework.Storage",
            "Microsoft.Xna.Framework.Xact",
            "Microsoft.Xna.Framework.GamerServices",
        ]

        for itemgroup in root.findall(tag("ItemGroup")):

            for reference in list(itemgroup.findall(tag("Reference"))):

                name = reference.attrib.get("Include", "")

                if any(x in name for x in xna_names):
                    print(f"  Removing {name}")
                    itemgroup.remove(reference)

        # -------------------------------------------------
        # Add FNA PackageReference
        # -------------------------------------------------

        has_fna = False

        for package in root.findall(f".//{tag('PackageReference')}"):

            if package.attrib.get("Include") == "FNA":
                has_fna = True

        if not has_fna:
            print("  Adding FNA package")

            package_group = ET.Element(tag("ItemGroup"))

            package = ET.SubElement(
                package_group,
                tag("PackageReference")
            )

            package.attrib["Include"] = "FNA"
            package.attrib["Version"] = FNA_VERSION

            root.append(package_group)

        # -------------------------------------------------
        # Write file
        # -------------------------------------------------

        ET.indent(tree, space="  ")

        tree.write(
            project_path,
            encoding="utf-8",
            xml_declaration=True
        )

        print("Done\n")

    # def convert_content(self, game:XBLIGGame):
    #     if game.decompiled is not None:
    #         folder = game.decompiled
    #         self.method_name(game)

    def convert_project_single_folder(self, folder):
        try:
            # backup project
            if (folder.parent.parent / "decompiled_backup").exists():
                shutil.rmtree(folder.parent.parent / "decompiled_backup")
            shutil.copytree(folder.parent, folder.parent.parent / "decompiled_backup")
            self.convert_xblig_to_fna(folder)
            self.add_xna_compat(folder.parent)
            self.remove_xna_usings(folder.parent)

        except Exception as e:
            print(
                f"FAILED {folder}: {e}"
            )

    # def method_name(self, game:XBLIGGame):
    #     if game.extracted is not None:
    #         folder = game.extracted
    #         content_folder = folder / "584E07D1" / "Content"
    #         # self.copy_content_folder(content_folder)
    #         output = content_folder.parent / "Content_Output"
    #         if content_folder.exists():
    #
    #         else:
    #             print(f"No Content folder found: {content_folder}")

    def convert_projects_all_folders(self, folder):
        """
        Convert every csproj below a folder.
        """

        projects = self.get_cs_project_folders(folder)

        print(f"Found {len(projects)} projects")

        for project in projects:
            try:
                self.convert_project_single_folder(project)
            except Exception as e:
                print(
                    f"FAILED {project}: {e}"
                )

    def get_cs_project_folders(self, folder) -> list[Path]:
        folder = Path(folder)

        return [
            csproj
            for csproj in folder.rglob("*.csproj")
        ]

    xna_using_files = [
        "Microsoft.Xna.Framework.Net",
        "Microsoft.Xna.Framework.GamerServices",
        "Microsoft.Xna.Framework.Storage"
    ]

    xna_net_types = [
        "PacketWriter",
        "PacketReader",
        "NetworkSession",
        "NetworkGamer",
        "LocalNetworkGamer",
        "AvailableNetworkSession"
    ]

    from pathlib import Path
    import shutil

    def add_xna_compat(self, project_folder):
        project_folder = Path(project_folder)

        compat_source = Path(get_app_dir() / "assets" / "XNACompat")

        compat_dest = project_folder / "XNACompat"

        compat_dest.mkdir(
            exist_ok=True
        )

        for file in compat_source.glob("*.cs"):
            shutil.copy(
                file,
                compat_dest / file.name
            )

        print(
            "Added XNA compatibility layer"
        )

    def remove_xna_usings(self, folder):
        folder = Path(folder)

        for cs in folder.rglob("*.cs"):

            text = cs.read_text(
                encoding="utf-8",
                errors="ignore"
            )

            original = text

            for u in self.xna_using_files:
                text = text.replace(
                    f"using {u};",
                    ""
                )

            if text != original:
                print("Patched", cs.name)

                cs.write_text(
                    text,
                    encoding="utf-8"
                )

    def log(self, message):
        print(message)


class XBLIG_Dialog(QDialog):

    def find_xblig_packages(self, root: str | Path, log=None):

        root = Path(root)
        games: list[XBLIGGame] = []

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
                decomp = package.parent / "extracted" / "decompiled"

                games.append(
                    XBLIGGame(
                        title=title,
                        folder_title=folder_title,
                        title_id=title_id,
                        virtual_title_id=xml_data.get("virtual_title_id"),
                        xml_title_id=xml_data.get("xml_title_id"),
                        content_type=content_type,
                        content_name="Xbox Live Indie Game",
                        package=package,
                        extracted=extracted if extracted.exists() else None,
                        game_root=extracted if extracted.exists() else package.parent,
                        exe=exe_file,
                        xml=game_info if game_info.exists() else None,
                        decompiled=decomp if decomp.exists() else None,
                    )
                )
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
        self.games: list[XBLIGGame] = []
        self.setWindowTitle("XBLIG Emulator")
        self.resize(1100, 750)

        self.build_ui()
        self.create_settings_drawer()
        self.apply_style()

        log_dir = get_app_dir() / "logs"
        log_dir.mkdir(exist_ok=True)
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            handlers=[
                logging.FileHandler(log_dir / "xenia_manager.log", encoding="utf-8"),
                logging.StreamHandler(sys.stdout),  # Console output
            ],
        )
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
    from typing import Optional

    def get_selected_game(self) -> Optional[XBLIGGame]:
        indexes = self.game_table.selectionModel().selectedRows()

        if not indexes:
            return None

        row = indexes[0].row()

        return self.games[row]

    from dataclasses import dataclass
    from pathlib import Path

    def get_random_games(self):
        random.seed(time.time())
        random.shuffle(self.games)
        random_project = self.games[0]
        return random_project

    def convert_selected_folders(self):
        game = self.get_selected_game()

        if not game:
            return

        decompiled = game.decompiled

        if decompiled is None:
            QMessageBox.warning(
                self,
                "Not Decompiled",
                "Please decompile the game first."
            )
            return

        converter = ConvertXnaProjects(get_app_dir(), self.log_message, self.games)
        converter.convert_project_single_folder(decompiled)

    def convert_folders(self):
        game = self.get_selected_game()
        root = get_app_dir() / "downloads" / "XBLIG"
        converter = ConvertXnaProjects(get_app_dir(), self.log_message, self.games)
        converter.convert_projects_all_folders(root)

    def convert_content(self):
        game = self.get_selected_game()
        if game is not None:
            root = get_app_dir() / "downloads" / "XBLIG"
            converter = ConvertXnaProjects(get_app_dir(), self.log_message, self.games)
            convert_xnb_folder_alba(game)

    def decompile_selected(self, game:XBLIGGame, open_explorer:bool=True):
        # game = self.get_selected_game()
        # if not game:
        #     return

        exe = game.exe
        if not exe:
            QMessageBox.warning(self, "No Executable", "Extract the game first.")
            return
        self.log_message(f"Generating Visual Studio project for {exe.name}...")

        try:
            project_dir = decompile_project(exe)
            game.decompiled = project_dir
        except subprocess.CalledProcessError as e:
            QMessageBox.critical(self, "ILSpy", str(e))
            return

        self.log_message("Visual Studio project created.")

        if open_explorer: subprocess.Popen(["explorer", str(project_dir)])

    from PySide6.QtCore import QObject, QThread, Signal

    class ScanWorker(QObject):

        finished = Signal(list)
        log = Signal(str)

        def __init__(self, root, scan_func, force=False):
            super().__init__()
            self.root = root
            self.force = force
            self.scan_func = scan_func

        from pathlib import Path

        def run(self):

            try:
                self.log.emit("Checking game cache...")

                games:list[XBLIGGame] = []
                current_mtime = get_folder_mtime(self.root)
                cache = None if self.force else load_cache()

                if cache and cache.get("mtime") == current_mtime:
                    games = cache["games"]
                    self.log.emit(f"Loaded {len(games)} games from cache.")
                else:
                    self.log.emit("Scanning folders...")
                    if not self.root.exists():
                        self.log.emit(f"Folder {self.root} does not exist.")
                    else:
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

        self.title_lbl.setText(game.title)

        self.titleid_lbl.setText(
            game.title_id or "-"
        )

        self.virtualid_lbl.setText(
            game.virtual_title_id or "-"
        )

        if game.exe:
            relative_path = game.exe.relative_to(root.parent)
            self.exe_lbl.setText(str(relative_path))
        else:
            self.exe_lbl.setText("-")

        if game.xml:
            relative_path = game.xml.relative_to(root.parent)
            self.xml_lbl.setText(str(relative_path))
        else:
            self.xml_lbl.setText("-")

        if not self.drawer_open:
            self.show_settings_drawer()

    def extract_missing(self):
        self.log_message(f"\nFound {len(self.games)} Xbox Live Indie Games\n")
        for i, game in enumerate(self.games, 1):

            # Auto extract missing games
            if game.extracted is None and game.package:

                extracted = self.extract_xblig_package(game)
                if extracted:
                    game.extracted = extracted
                    self.log_message(f"Extracted {game.title} Successfully")
                    save_cache(self.games)
            else:
                self.log_message(f"Skipping {game.title}")

    def log_message(self, message):
        self.log_window.append(message)

    def log_message_log(self, message):
        logging.info(f"{message}")

    def extract_xblig_package(self, game: XBLIGGame):
        package = game.package

        if not package:
            return None

        package = Path(package)

        if not package.exists():
            print(f"Package missing: {package}")
            return None

        from stfs_extract import extract_live_pirs

        # Create extracted folder beside package
        extracted_path = package.parent / "extracted"

        extracted_path.mkdir(parents=True, exist_ok=True)

        try:
            from contextlib import redirect_stdout

            with redirect_stdout(QtLogger(self.log_message_log)):
                extract_live_pirs(package, extracted_path)

            print(f"Extracted to: {extracted_path}")

        except Exception as e:
            print(f"Extraction failed: {e}")
            return None

        return extracted_path

    def load_games(self, games: list[XBLIGGame]):
        self.game_table.setRowCount(0)

        for game in games:
            row = self.game_table.rowCount()
            self.game_table.insertRow(row)

            ready = game.exe is not None and game.xml is not None
            status = "Ready" if ready else "Needs Build"

            columns = [
                "Title",
                "Status",
                "Extracted",
                "Decompiled",
                "Executable",
                "Content Converted",
                "Content Format"
            ]

            d = game.decompiled.name if game.decompiled else ""

            self.game_table.setItem(row, 0, QTableWidgetItem(game.title))
            self.game_table.setItem(row, 1, QTableWidgetItem(status))
            self.game_table.setItem(row, 2, QTableWidgetItem("Yes" if game.extracted else "No"))
            self.game_table.setItem(row, 4, QTableWidgetItem(game.exe.name if game.exe else ""))
            self.game_table.setItem(row, 3, QTableWidgetItem(d))
            self.game_table.setItem(row, 5, QTableWidgetItem(game.content_converted))
            self.game_table.setItem(row, 6, QTableWidgetItem(game.content_format))

    from PySide6.QtWidgets import (
        QDialog,
        QVBoxLayout,
        QGroupBox,
        QCheckBox,
        QPushButton,
        QHBoxLayout,
        QApplication,
    )

    class BuildSelectedDialog(QDialog):
        def __init__(self, parent=None):
            super().__init__(parent)

            self.setWindowTitle("Build Selected Game")
            self.resize(420, 280)

            layout = QVBoxLayout(self)

            # Build options
            options_group = QGroupBox("Build Options")
            options_layout = QVBoxLayout(options_group)

            self.decompile_check = QCheckBox("Decompile executable")
            self.convert_csproj_check = QCheckBox("Convert project (.csproj)")
            self.convert_content_check = QCheckBox("Convert XNA content")
            self.open_vs_check = QCheckBox("Open project in Visual Studio")
            self.open_explorer_check = QCheckBox("Open project folder in Explorer")

            # Sensible defaults
            self.decompile_check.setChecked(True)
            self.convert_csproj_check.setChecked(True)
            self.convert_content_check.setChecked(True)

            options_layout.addWidget(self.decompile_check)
            options_layout.addWidget(self.convert_csproj_check)
            options_layout.addWidget(self.convert_content_check)
            options_layout.addWidget(self.open_vs_check)
            options_layout.addWidget(self.open_explorer_check)

            layout.addWidget(options_group)

            layout.addStretch()

            # Buttons
            button_layout = QHBoxLayout()
            button_layout.addStretch()

            self.run_button = QPushButton("Run")
            self.cancel_button = QPushButton("Cancel")

            self.run_button.clicked.connect(self.accept)
            self.cancel_button.clicked.connect(self.reject)

            button_layout.addWidget(self.run_button)
            button_layout.addWidget(self.cancel_button)

            layout.addLayout(button_layout)

        def options(self):
            """Return selected options."""
            return {
                "decompile": self.decompile_check.isChecked(),
                "convert_csproj": self.convert_csproj_check.isChecked(),
                "convert_content": self.convert_content_check.isChecked(),
                "open_visual_studio": self.open_vs_check.isChecked(),
                "open_explorer": self.open_explorer_check.isChecked(),
            }


    def build_selected(self):
        game = self.get_selected_game()
        if not game:
            return
        if game.extracted is None:
            self.log_message("Extracted game not found.")
            return
        # decompile options
        # convert csproj
        # convert content
        # open in visual studio
        # open in explorer
        # run button cancel button
        dlg = self.BuildSelectedDialog()
        if not dlg.exec():
            return

        options = dlg.options()

        if options["decompile"]:
            self.log_message("Decompiling selected game...")
            self.decompile_selected(game)
            assert game.decompiled is not None
            content_dir = game.extracted / "584E07D1" / "Content"
            copy_content_folder(
                content_dir,
                game.decompiled / "Content",
            )

        # if options["convert_content"]:
        #
        # if options["convert_csproj"]:
        #
        # if options["open_visual_studio"]:

        # folder = game.extracted
        # content_dir = folder / "584E07D1" / "Content"
        # assert game.decompiled is not None
        # copy_content_folder(content_dir, game.decompiled / "Content")

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

        self.build_btn = QPushButton("Decompile Game")
        self.build_btn.clicked.connect(self.build_selected)

        self.random_btn = QPushButton("Random Game")
        self.random_btn.clicked.connect(self.build_selected)

        # self.build_content_btn = QPushButton("Convert Content")
        # self.build_content_btn.clicked.connect(self.convert_content)
        #
        # self.convert_one_btn = QPushButton("Convert (Selected) Game to FNA Project")
        # self.convert_one_btn.clicked.connect(self.convert_selected_folders)

        self.convert_all_btn = QPushButton("Convert (All Unconverted) Game to FNA Project")
        self.convert_all_btn.clicked.connect(self.convert_folders)

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
        toolbar.addWidget(self.convert_all_btn)
        toolbar.addWidget(self.launch_btn)
        toolbar.addWidget(self.refresh_btn)
        toolbar.addWidget(self.open_folder_btn)
        toolbar.addWidget(self.close_btn)
        toolbar.addWidget(self.random_btn)
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

        self.game_table = QTableWidget(0, 7)

        columns = [
            "Title",
            "Status",
            "Extracted",
            "Decompiled",
            "Executable",
            "Content Converted",
            "Content Format"
        ]
        self.game_table.setHorizontalHeaderLabels(columns)

        header = self.game_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)

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


