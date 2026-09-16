import io
import os
import random
import shutil
import subprocess
import sys
import threading
import time
import traceback
import xml.etree.ElementTree as ET  # noqa: N812
from contextlib import redirect_stdout
from functools import partial
from glob import escape
from io import StringIO
from pathlib import Path
from typing import Callable, cast

from PIL import Image
from PySide6.QtCore import QPropertyAnimation, QEasingCurve, QThread, Signal, QObject, QModelIndex, \
    Slot, QProcess, QEvent
from PySide6.QtGui import QFont, QMouseEvent, QPixmap, QPainter
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QWidget,
    QPushButton,
    QLabel,
    QFormLayout,
    QGroupBox,
    QHeaderView, QApplication, QSizePolicy, QFrame, QGraphicsDropShadowEffect, QCheckBox, QButtonGroup,
    QRadioButton, QProgressBar, QPlainTextEdit, QLineEdit, QAbstractItemView, QTableView, QFileDialog,
)

from config import get_app_dir, load_config, save_config
from db import ConversionResult, Database, XBLIGGame, GameSource
from logging_setup import setup_logger
from moby_games import MobyGamesClient
from models.model_indie import IndieGameTableModel


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


def open_solution(project_dir: Path):
    for csproj in project_dir.glob("*.csproj"):
        os.startfile(csproj)
        return


DECOMPILER = get_app_dir() / "assets" / "tools"
ILSPY_GUI = DECOMPILER / "ILSpy" / "release" / "win-x64" / "ILSpy.exe"
ILSPY_CMD = DECOMPILER / "ILSpyCmd" / "Release" / "net10.0" / "ilspycmd.exe"


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

    root = Path("D:/") / "downloads" / "XBLIG"

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


def decompress_content_archives(source_content_root_folder: Path | None, log_callback=None):
    if source_content_root_folder is None:
        return
    if not source_content_root_folder.exists():
        archives = sorted(source_content_root_folder.parent.glob("Content*.7z"))
        if archives:
            log_callback(f"Content folder missing, extracting {len(archives)} archive(s)...", "success")
            for archive in archives:
                decompress_content(archive, source_content_root_folder.parent, log_callback=log_callback)
        else:
            raise FileNotFoundError(
                f"Content folder or archive not found: {source_content_root_folder}"
            )

    # if dest_content_folder.exists() and dest_content_folder.is_dir():
    #     shutil.rmtree(dest_content_folder, ignore_errors=True)

    def copy_with_log(src, dst):
        log_callback(f"Copying: {src} -> {dst}")
        return shutil.copy2(src, dst)

    # shutil.copytree(
    #     source_content_root_folder,
    #     dest_content_folder,
    #     copy_function=copy_with_log,
    # )


def get_7zip() -> Path:
    seven_zip = (
            get_app_dir()
            / "assets"
            / "zip"
            / "7z.exe"
    )

    if not seven_zip.exists():
        raise FileNotFoundError(f"7-Zip not found: {seven_zip}")

    return seven_zip


def decompress_content(archive: Path, output_dir: Path | None = None, delete_archive: bool = False, log_callback=None,
                       show_command=False) -> Path:
    archive = Path(archive)

    if output_dir is None:
        output_dir = archive.parent

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    arguments = [get_7zip(), "x", str(archive), f"-o{output_dir}", "-y"]

    if show_command: log_callback(f"7-zip command: {arguments}", "success")
    subprocess.run(arguments, check=True)
    log_callback(f"Decompression Completed", "success")
    if delete_archive: archive.unlink()
    return output_dir


def compress_folders(root: Path, source_dirs, archive: Path, delete_original: bool = False, log_callback=None) -> Path:
    source_dirs = [source_dirs] if isinstance(source_dirs, Path) else [Path(p) for p in source_dirs]

    if log_callback:
        log_callback("Compressing: " + ", ".join(map(str, source_dirs)), "success")

    relative_folders = [folder.relative_to(root) for folder in source_dirs]
    command = [str(get_7zip()), "a", "-t7z", "-mx=9", "-m0=lzma2", "-mmt=on", "-ms=on"]
    if delete_original: command.append("-sdel")

    command += [str(archive), *map(str, relative_folders)]

    process = subprocess.Popen(
        command,
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    assert process.stdout is not None

    while True:
        line = process.stdout.readline()

        if not line and process.poll() is not None:
            break

        if line:
            log_callback(line.rstrip(), "Success")

    return_code = process.wait()

    if return_code != 0:
        log_callback(f"7-Zip failed with exit code: {return_code:#010x}", "success")

    if delete_original:
        for source_dir in source_dirs:
            if source_dir.exists():
                shutil.rmtree(source_dir)

    return archive


def ensure_tool_extracted(name: str, log_callback=None):
    tools_root = get_app_dir() / "assets" / "tools"

    relative_path = TOOL_PATHS[name]
    folder = tools_root / relative_path
    archive = tools_root / f"{name}.7z"

    if folder.exists():
        return

    if not archive.exists(): raise FileNotFoundError(f"Tool archive not found: {archive}")

    folder.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        [
            str(get_7zip()),
            "x",
            str(archive),
            "-y",
        ],
        cwd=folder,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if log_callback:
        for line in result.stdout.splitlines():
            if line.strip():
                log_callback(line)


def compress_tool(name: str):
    tools_root = get_app_dir() / "assets" / "tools"

    relative_path = TOOL_PATHS[name]
    folder = tools_root / relative_path
    archive = tools_root / f"{name}.7z"

    if not folder.exists():
        print(f"Tool '{name}' not found: {folder}")
        return

    if archive.exists():
        archive.unlink()

    subprocess.run(
        [
            str(get_7zip()),
            "a",
            "-t7z",
            "-mx=9",
            "-m0=lzma2",
            "-mmt=on",
            "-ms=on",
            str(archive),
            "."
        ],
        cwd=folder,
        check=True,
    )


TOOL_PATHS = {
    "ilspycmd": Path("ilspycmd"),
    "ilspy": Path("ilspy"),
    "conversion": Path("conversion"),
    "vgmstream": Path("vgmstream"),
}


def get_tool_path(name: str) -> Path:
    try:
        return TOOL_PATHS[name]
    except KeyError:
        raise ValueError(f"Unknown tool: {name}")


def cleanup_tool(name: str, log=None):
    tools_root = get_app_dir() / "assets" / "tools"

    relative_path = get_tool_path(name)
    folder = tools_root / relative_path

    if not folder.exists():
        return

    try:
        shutil.rmtree(folder)
        if log: log(f"Cleaned up: {folder}")
    except PermissionError as e:
        if log: log(f"Cleanup failed for {folder}: {e}")


class ToolManager:

    def __init__(self, *tools: str):
        self.tools = tools

    def extract(self):
        for tool in self.tools:
            ensure_tool_extracted(tool, None)

    def cleanup(self):
        for tool in self.tools:
            cleanup_tool(tool, None)

    def __enter__(self):
        self.extract()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.cleanup()


def add_xna_compat(project_folder):
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


alba = (get_app_dir() / "assets/tools/conversion/Alba.XnaConvert.0.1.2/Alba.XnaConvert.exe")
xnb_cli = (get_app_dir() / "assets/tools/conversion/xnbcli-windows-x64/xnbcli.exe")
xnb_extractor = (get_app_dir() / "assets/tools/conversion/xnb-extractor/Release/net481/XnbExtractor.exe")


def create_launch_settings(project_path: Path, game_title=None):
    launch_settings_path = project_path / "Properties" / "launchSettings.json"
    launch_settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings = {
        "profiles": {
            f"{game_title}": {
                "commandName": "Project",
                "debugEngines": "managed-dotnet,native",
            }
        }
    }
    launch_settings_path.write_text(json.dumps(settings, indent=2), encoding="utf-8", )


RAINBOW_COLORS = [
    # ── Reds ─────────────────────────────────────────────
    "#FF4D4D",
    "#FF5252",
    "#FF5C5C",
    "#FF6666",
    "#FF7070",
    "#FF7A7A",
    "#FF4757",
    "#FF3F4F",
    "#FF3850",
    "#FF3048",

    # ── Red → Orange ─────────────────────────────────────
    "#FF493D",
    "#FF5138",
    "#FF5933",
    "#FF6130",
    "#FF692B",
    "#FF7025",
    "#FF7820",
    "#FF801B",
    "#FF8816",
    "#FF9011",

    # ── Oranges ───────────────────────────────────────────
    "#FF9810",
    "#FFA00F",
    "#FFA80E",
    "#FFB00D",
    "#FFB80C",
    "#FFC00B",
    "#FFC70A",
    "#FFCE0A",
    "#FFD50A",
    "#FFDC0A",

    # ── Yellows ──────────────────────────────────────────
    "#FFE20A",
    "#FFE80A",
    "#FFEE0A",
    "#FFF30A",
    "#FFF80A",
    "#FFFC12",
    "#F8FF18",
    "#EEFF20",
    "#E4FF27",
    "#DAFF2E",

    # ── Yellow → Green ───────────────────────────────────
    "#D0FF35",
    "#C4FF3C",
    "#B8FF43",
    "#ACFF4A",
    "#A0FF51",
    "#94FF58",
    "#88FF5F",
    "#7CFF66",
    "#70FF6D",
    "#64FF74",

    # ── Greens ───────────────────────────────────────────
    "#58FF7B",
    "#4CFF82",
    "#40FF89",
    "#34FF90",
    "#28FF97",
    "#20FF9E",
    "#18FFA5",
    "#10FFAC",
    "#08FFB3",
    "#00FFBA",

    # ── Cyan ─────────────────────────────────────────────
    "#00F8C4",
    "#00F0CE",
    "#00E8D8",
    "#00E0E2",
    "#00D8EC",
    "#00D0F6",
    "#00C8FF",
    "#00BFFF",
    "#18B7FF",
    "#30AFFF",

    # ── Blues ────────────────────────────────────────────
    "#48A7FF",
    "#60A0FF",
    "#7898FF",
    "#9090FF",
    "#8888FF",
    "#8080FF",
    "#7878FF",
    "#7070FF",
    "#6868FF",
    "#6060FF",

    # ── Blue → Purple ────────────────────────────────────
    "#6858FF",
    "#7050FF",
    "#7848FF",
    "#8040FF",
    "#8838FF",
    "#9030FF",
    "#9828FF",
    "#A020FF",
    "#A818FF",
    "#B010FF",

    # ── Purples / Magentas ───────────────────────────────
    "#B818FF",
    "#C020FF",
    "#C828FF",
    "#D030FF",
    "#D838FF",
    "#E040FF",
    "#E848FF",
    "#F050FF",
    "#F858FF",
    "#FF60FF",
]


class ConvertXnaProjects(QObject):
    log_signal = Signal(str, str, bool)
    progress_signal = Signal(int, int)
    finished_signal = Signal(ConversionResult)
    total_files_signal = Signal(int)

    def __init__(self, project_path, games=None, options=None):
        super().__init__()

        self.compress_thread = None
        self.extracted = None
        self._rainbow_index = 1
        self.config = load_config()
        self.options: dict[str, QCheckBox] = options
        self.project_path = Path(project_path)
        self.games = games

    def signal_log_message(self, message, color=None):
        if color is None:
            color = RAINBOW_COLORS[self._rainbow_index]
            self._rainbow_index = (self._rainbow_index + 1) % len(RAINBOW_COLORS)
        self.log_signal.emit(message, color, False)

    from pathlib import Path
    def find_packages(self, root_folders: list[Path]) -> list[XBLIGGame]:

        games: list[XBLIGGame] = []

        indie_games_path = Path(self.config["indie_games_path"])
        solution_path = Path(self.config["indie-game-solution-location"])
        archive_base = solution_path.parent / "indie-game-archive"

        title_folders: list[Path] = []
        total_files = 0
        total_folders = 0
        files_scanned = 0

        def parse_xml(xml_file: Path) -> dict:
            if not xml_file.is_file():
                return {}

            try:
                root_element = ET.parse(xml_file).getroot()
            except (ET.ParseError, OSError):
                return {}

            title_info = root_element.find(".//TitleInfo")
            if title_info is None:
                return {}

            return {
                "title": title_info.get("Name"),
                "virtual_title_id": title_info.get("VirtualTitleID"),
                "xml_title_id": title_info.get("TitleID"),
                "image_path": title_info.get("ImagePath"),
            }

        target_dirs = {
            "4D530888",
            "584E07D2",
            "00000002",
            "584E07D1",
            "BIN",
            "CONTENT",
        }

        for root in root_folders:
            root = Path(root)

            self.signal_log_message(f"Scanning: {root}")

            for current_root, dirs, files in os.walk(root):
                current_path = Path(current_root)

                total_folders += len(dirs)
                total_files += len(files)

                found = False

                for directory in list(dirs):
                    if directory.upper() in target_dirs:
                        title_folders.append(current_path)
                        dirs.clear()
                        found = True
                        break

                if found:
                    continue

                self.progress_signal.emit(
                    files_scanned,
                    max(total_files, 1),
                )

        self.total_files_signal.emit(total_files)

        self.signal_log_message(f"Found {len(title_folders):,} Indie Game Folders")

        for index, package in enumerate(title_folders, start=1):

            folder_title = package.name

            game_info = package / "GameInfo.xml"
            xml_data = parse_xml(game_info)

            title = xml_data.get("title") or folder_title
            title_id = xml_data.get("xml_title_id") or folder_title
            game_id = xml_data.get("game_id") or folder_title
            # -----------------------------------------------------
            # Runtime profile
            # -----------------------------------------------------

            profile_file = package / "Microsoft.Xna.Framework.RuntimeProfile"

            content_format = ""

            if profile_file.is_file():
                try:
                    content_format = profile_file.read_text(encoding="utf-8").strip()
                except OSError:
                    pass

            # -----------------------------------------------------
            # Create game
            # -----------------------------------------------------

            game = XBLIGGame(
                title=title,
                folder_title=folder_title,
                title_id=title_id,
                game_id=str(game_id),
                virtual_title_id=xml_data.get("virtual_title_id"),
                xml_title_id=xml_data.get("xml_title_id"),
                content_type=content_format,
                content_name="Xbox Live Indie Game",
                content_format=content_format,
                package=package,
            )

            # -----------------------------------------------------
            # Set paths
            # -----------------------------------------------------

            extracted = indie_games_path / folder_title
            archived = archive_base / folder_title

            game.extracted = package
            game.archived = archived
            game.game_root = package

            archived_state, extracted_state, game_folder_status, cs_proj_files_extracted = folder_status(game)
            # if not archived_state: game.archived = None
            # if not extracted_state: game.extracted = None
            games.append(game)

            self.progress_signal.emit(index, max(len(title_folders), 1))

        self.signal_log_message(f"Scanner complete: {len(games):,} games")
        return games

    def extract_packages(self, root_folders: list[Path]) -> list[XBLIGGame]:

        games: list[XBLIGGame] = []
        packages: list[Path] = []

        headers = {b"CON ", b"LIVE", b"PIRS"}
        indie_games_path = Path(self.config["indie_games_path"])
        solution_path = Path(self.config["indie-game-solution-location"])
        archive_base = solution_path.parent / "indie-game-archive"

        total_files = 0
        total_folders = 0
        files_scanned = 0

        def is_package(path: Path) -> bool:
            try:
                with path.open("rb") as f:
                    return f.read(4) in headers
            except (OSError, PermissionError):
                return False

        def parse_xml(xml_file: Path) -> dict:
            if not xml_file.is_file():
                return {}

            try:
                tree = ET.parse(xml_file)
                root_element = tree.getroot()

                title_info = root_element.find(".//TitleInfo")

                if title_info is None:
                    return {}

                image_path = title_info.findtext("ImagePath")

                return {
                    "title": title_info.findtext("Title"),
                    "virtual_title_id": title_info.findtext("VirtualTitleId"),
                    "xml_title_id": title_info.findtext("TitleId"),
                    "image_path": image_path,
                }

            except (ET.ParseError, OSError):
                return {}

        for root in root_folders:
            root = Path(root)

            self.signal_log_message(f"Scanning: {root} for Packages")
            target_dirs = {"4D530888", "584E07D2", "00000002"}

            for current_root, dirs, files in os.walk(root):
                current_path = Path(current_root)

                total_folders += len(dirs)
                total_files += len(files)

                if current_path.name.upper() in target_dirs:
                    for filename in files:
                        path = current_path / filename

                        print(f"Scanning file: {path}")
                        files_scanned += 1

                        if is_package(path):
                            packages.append(path)
                            self.signal_log_message(f"Found package: {path}")

                self.progress_signal.emit(
                    files_scanned,
                    max(total_files, 1),
                )

                if total_files and total_files % 1000 == 0:
                    self.signal_log_message(f"Scanner: {total_files} files, {total_folders} folders")

            self.total_files_signal.emit(total_files)

            self.signal_log_message(f"Found {len(packages)} Indie Game Packages")

            for index, package in enumerate(packages):
                folder_title = package.parent.parent.parent.name
                title = folder_title
                game = XBLIGGame(
                    title=title,
                    folder_title=folder_title,
                    package=package,
                    game_root=package.parent.parent.parent
                )
                self.signal_log_message(f"Extracting {game.title}")
                self.extract_package(game, False, overwrite=False)
                games.append(game)

        self.signal_log_message(f"Scanner complete: {len(games):,} games")
        return games

    def extract_package(self, game: XBLIGGame, worker: bool = False, overwrite=False):
        assert game.package is not None
        package = Path(game.package)

        self.signal_log_message(f"Extracting {game.title}")
        from stfs_extract import extract_live_pirs
        assert game.folder_title is not None

        extracted_path = game.game_root

        game.extracted = extracted_path
        game.package = package
        self.extracted = extracted_path

        # if not overwrite and game.extracted is not None:
        #     self.signal_log_message(f"{game.title} Already Extracted")
        #     return
        #
        if not overwrite and extracted_path.exists() and (extracted_path / "584E07D1").exists() and any(
                (extracted_path / "584E07D1").iterdir()):
            self.signal_log_message(f"Not Extracting {game.title} it has already been extracted. Check Overwrite if required.")
            return game.game_root
        extracted_path.mkdir(parents=True, exist_ok=True)

        try:
            from contextlib import redirect_stdout
            from functools import partial
            if worker:
                func = partial(extract_live_pirs, package, extracted_path, None)
                self.run_worker(func)
            else:
                # extract_live_pirs(package, extracted_path, log = self.log_message, selected_ids=None)
                run_powershell_script(game, script=2, log_message=self.signal_log_message)

            self.signal_log_message(f"Extracted to: {extracted_path}")

        except Exception as e:
            self.signal_log_message(f"Extraction failed for {game.title}: {type(e).__name__}: {e}")
            self.signal_log_message(traceback.format_exc())
            return extracted_path

        return extracted_path

    def run_worker(self, func: Callable[..., None] | Callable[..., None]):
        thread = QThread(self)
        self.compress_thread = thread
        worker = CompressWorker(func)
        self.compress_worker = worker
        worker.log.connect(self.signal_log_message)
        worker.finished.connect(self.compress_thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._worker_finished)

        worker.moveToThread(self.compress_thread)
        thread.started.connect(worker.run)
        self.compress_thread.start()

    def _worker_finished(self) -> None:
        # self.game.extracted = self.extracted
        # self.game.executables = list(self.extracted.rglob("*.exe"))

        save_cache(self.games)
        # self.load_games(self.games)

    def convert_xnb_folder_tools(self, game: XBLIGGame, tool_id: int = 1):

        if game.extracted is None:
            self.signal_log_message(f"Game not extracted: {game}")
            return None

        content_dir = game.extracted / "584E07D1" / "Content"
        output_dir = content_dir.parent / "Content_Output"

        if not content_dir.exists():
            self.signal_log_message(f"Content folder not found: {content_dir}")
            return None

        # alba = (get_app_dir() / "assets/tools/conversion/Alba.XnaConvert.0.1.2/Alba.XnaConvert.exe")
        # xnb_cli = (get_app_dir() / "assets/tools/conversion/xnbcli-windows-x64/xnbcli.exe")
        # xnb_extractor = (get_app_dir() / "assets/tools/conversion/xnb-extractor/Release/net481/XnbExtractor.exe")

        failed_folders = []

        if tool_id == 1:
            tool_name = "Alba"
            cmd = [
                str(alba),
                "convert",
                "-v", "4",
                "-d", str(content_dir),
                "-o", str(output_dir),
                "-r",
            ]

        elif tool_id == 2:
            tool_name = "xnbcli"
            cmd = [
                str(xnb_cli),
                "unpack",
                str(content_dir),
                str(output_dir),
            ]
        elif tool_id == 3:
            tool_name = "xnb_extractor"
            cmd = [
                str(xnb_extractor),
                "--input", str(content_dir),
                "--output", str(output_dir),
            ]

            for option, checkbox in self.options.items():
                if checkbox.isChecked():
                    cmd.append(f"--{option}")
        else:
            self.signal_log_message(f"Unknown tool id: {tool_id}")
            return None

        self.signal_log_message(f"Running {tool_name}...")

        try:
            stdout_lines = []
            stderr_lines = []

            self.signal_log_message("Full command:")
            self.signal_log_message(" ".join(cmd))

            with subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
            ) as process:

                assert process.stdout is not None
                assert process.stderr is not None

                for line in process.stdout:
                    line = line.rstrip()
                    stdout_lines.append(line)
                    self.signal_log_message(line)

                for line in process.stderr:
                    line = line.rstrip()
                    stderr_lines.append(line)
                    self.signal_log_message(f"ERR: {line}")

                process.wait()

            stdout = "\n".join(stdout_lines)
            stderr = "\n".join(stderr_lines)

            # Find generated files
            output_files = []

            if output_dir.exists():
                output_files = [
                    f for f in output_dir.rglob("*")
                    if f.is_file()
                ]

            # Determine success
            success = (
                    process.returncode == 0
                    and len(output_files) > 0
            )

            result = ConversionResult(
                tool=tool_name,
                success=success,
                input_file=content_dir,
                output_files=output_files,
                stdout=stdout,
                stderr=stderr,
            )

            self.signal_log_message(
                f"{tool_name}: {'SUCCESS' if success else 'FAILED'}"
            )

            self.signal_log_message(
                f"Generated files: {len(output_files)}"
            )

            if not success:
                failed_folders.append(content_dir)

            self.finished_signal.emit(result)

        except Exception as e:

            failed_folders.append(content_dir)

            self.signal_log_message(
                f"ERROR running {tool_name}: {e}"
            )

            result = ConversionResult(
                tool=tool_name,
                success=False,
                input_file=content_dir,
                output_files=[],
                stdout="",
                stderr="",
                error=str(e),
            )

            self.finished_signal.emit(result)

        self.signal_log_message("===================")
        self.signal_log_message("Conversion complete")
        self.signal_log_message(
            f"Failed folders: {len(failed_folders)}"
        )

        for folder in failed_folders:
            self.signal_log_message(str(folder))

        return result

    LANGUAGE_FOLDERS = {
        "de", "es", "fr", "it", "pt", "ru",
        "ja", "ko", "zh", "nl", "pl",
        "cs", "da", "fi", "nb", "sv",
    }

    def clean_csproj(self, project_path: Path, game_dll_files: list[Path], game=None, resx_files=None) -> None:
        project_path = Path(project_path)

        self.signal_log_message(f"Updating project: {project_path}")
        self.signal_log_message(f"  Project path: {project_path}")
        create_launch_settings(project_path.parent, game.folder_title)
        with open(project_path, "rb") as f:
            tree = ET.parse(f)
        root = tree.getroot()

        # ---------------------------------------------------------
        # MSBuild namespace
        # ---------------------------------------------------------

        ns = root.tag.split("}")[0] + "}" if root.tag.startswith("{") else ""

        def tag(name: str) -> str:
            return f"{ns}{name}"

        # ---------------------------------------------------------
        # Preserve AssemblyName
        # ---------------------------------------------------------

        # assembly_name = next(
        #     (
        #         assembly.text.strip()
        #         for group in root.findall(tag("PropertyGroup"))
        #         for assembly in [group.find(tag("AssemblyName"))]
        #         if assembly is not None and assembly.text
        #     ),
        #     None,
        # )
        #
        # if assembly_name:
        #     self.log_message(f"  Preserving AssemblyName: {assembly_name}")
        # else:
        #     self.log_message("  No AssemblyName found; using project default.")

        # ---------------------------------------------------------
        # Remove existing PropertyGroups / ItemGroups
        # ---------------------------------------------------------

        removed_properties = removed_items = 0

        for element in list(root):
            name = element.tag.split("}")[-1]

            if name == "PropertyGroup":
                root.remove(element)
                removed_properties += 1
            elif name == "ItemGroup":
                root.remove(element)
                removed_items += 1

        self.signal_log_message(
            f"  Removed {removed_properties} PropertyGroup(s) "
            f"and {removed_items} ItemGroup(s)."
        )

        # ---------------------------------------------------------
        # Properties
        # ---------------------------------------------------------

        prop_group = ET.SubElement(root, tag("PropertyGroup"))

        assembly_name = game.title
        if assembly_name:
            ET.SubElement(prop_group, tag("AssemblyName")).text = assembly_name

        import re

        def find_startup_object(game: XBLIGGame) -> tuple[str | None, str | None]:
            self.signal_log_message(
                f"Finding startup object for {game.title}",
                color="blue",
            )

            program = next(game.game_root.rglob("Program.cs"), None)

            if program:
                text = program.read_text(encoding="utf-8", errors="ignore")

                namespace = re.search(r"\bnamespace\s+([\w.]+)", text)
                main_class = re.search(
                    r"\b(?:static\s+)?class\s+(\w+).*?\bstatic\s+void\s+Main\s*\(",
                    text,
                    re.DOTALL,
                )

                if namespace and main_class:
                    return namespace.group(1), f"{namespace.group(1)}.{main_class.group(1)}"

            # Fallback: find the class inheriting from Game
            for source in game.game_root.rglob("*.cs"):
                text = source.read_text(encoding="utf-8", errors="ignore")

                namespace = re.search(r"\bnamespace\s+([\w.]+)", text)
                game_class = re.search(
                    r"\bclass\s+(\w+)\s*:\s*(?:[\w.]+\.)?Game\b",
                    text,
                )

                if game_class:
                    rns = namespace.group(1) if namespace else None
                    class_name = game_class.group(1)

                    suo = f"{rns}.{class_name}" if rns else class_name

                    self.signal_log_message(
                        f"Found Game class: {suo} ({source.name})",
                        color="blue",
                    )

                    return rns, suo

            return None, None

        rns, suo = find_startup_object(game)

        properties = {
            "GenerateAssemblyInfo": "false",
            "TargetFramework": "net9.0-windows",
            "ImplicitUsings": "enable",
            "Nullable": "enable",
            "OutputType": "WinExe",
            "LangVersion": "13.0",
            "AllowUnsafeBlocks": "True",
            "CheckForOverflowUnderflow": "False",
            "EnableDefaultEmbeddedResourceItems": "False",
            "PlatformTarget": "x86",
            "Platforms": "x86;x64",
            "RootNamespace": rns or game.title,
            "ApplicationIcon": "DashboardIcon.ico",
        }

        if suo:
            properties["StartupObject"] = suo

        def png_to_ico(png_path: Path, ico_path: Path | None = None) -> Path:
            png_path = Path(png_path)
            ico_path = ico_path or png_path.with_suffix(".ico")

            with Image.open(png_path) as image:
                image.save(ico_path, format="ICO")

            return ico_path

        self.signal_log_message("Creating game thumbnail icon")
        png_to_ico(Path(project_path.parent / "DashboardIcon.png"), Path(project_path.parent / "DashboardIcon.ico"))

        for name, value in properties.items():
            ET.SubElement(prop_group, tag(name)).text = value
            self.signal_log_message(f"    {name} = {value}")

        # ---------------------------------------------------------
        # Contents.csproj
        # ---------------------------------------------------------

        solution_path = Path(self.config["indie-game-solution-location"])
        content_project = solution_path.parent / "Content-References/FNA.Contents.csproj"
        self.signal_log_message(f"Adding project reference: {content_project}")

        item_group = ET.SubElement(root, tag("ItemGroup"))

        reference = ET.SubElement(
            item_group,
            tag("ProjectReference"),
            {"Include": str(content_project)},
        )

        ET.SubElement(reference, tag("Private")).text = "True"
        ET.SubElement(
            reference,
            tag("CopyLocalSatelliteAssemblies"),
        ).text = "True"

        # ---------------------------------------------------------
        # Game DLL references
        # ---------------------------------------------------------

        if game_dll_files:
            normal_dlls = []
            satellite_dlls = []

            for dll in game_dll_files:
                try:
                    relative_path = dll.relative_to(project_path.parent)
                    parts = relative_path.parts
                except ValueError as e:
                    self.signal_log_message(f"Error Adding DLL {str(dll)} relative to {str(project_path)}")
                    continue

                is_satellite = (
                        dll.name.lower().endswith(".resources.dll")
                        or (
                                len(parts) > 1
                                and parts[0].lower() in self.LANGUAGE_FOLDERS
                        )
                )

                if is_satellite:
                    satellite_dlls.append((dll, relative_path))
                else:
                    normal_dlls.append((dll, relative_path))

            # ---------------------------------------------------------
            # Normal DLL references
            # ---------------------------------------------------------

            if normal_dlls:
                self.signal_log_message(f"  Adding {len(normal_dlls)} game DLL reference(s)...")

                dll_group = ET.SubElement(root, tag("ItemGroup"))

                for dll, relative_path in normal_dlls:
                    reference = ET.SubElement(
                        dll_group,
                        tag("Reference"),
                        {"Include": dll.stem},
                    )

                    ET.SubElement(
                        reference,
                        tag("HintPath"),
                    ).text = relative_path.as_posix()

                    ET.SubElement(
                        reference,
                        tag("Private"),
                    ).text = "True"

            # ---------------------------------------------------------
            # Satellite DLLs
            # ---------------------------------------------------------

            if satellite_dlls:
                self.signal_log_message(
                    f"  Adding {len(satellite_dlls)} satellite DLL(s) "
                    "to output..."
                )

                satellite_group = ET.SubElement(
                    root,
                    tag("ItemGroup"),
                )

                for dll, relative_path in satellite_dlls:
                    resource = ET.SubElement(
                        satellite_group,
                        tag("None"),
                        {"Include": relative_path.as_posix()},
                    )

                    ET.SubElement(
                        resource,
                        tag("CopyToOutputDirectory"),
                    ).text = "PreserveNewest"

        resx_group = ET.SubElement(root, tag("ItemGroup"))
        for resx in resx_files:
            resx = Path(resx)
            try:
                relative_path = resx.relative_to(project_path.parent).as_posix()
                ET.SubElement(
                    resx_group,
                    tag("EmbeddedResource"),
                    {"Include": relative_path},
                )
            except ValueError:
                self.signal_log_message(
                    f"Error adding DLL {resx} relative to {project_path.parent}"
                )
                continue

        # ---------------------------------------------------------
        # Content files
        # ---------------------------------------------------------

        self.signal_log_message(
            r"  Configuring Content\**\* to always copy to output..."
        )

        content_group = ET.SubElement(root, tag("ItemGroup"))

        none = ET.SubElement(
            content_group,
            tag("None"),
            {"Update": r"Content\**\*"},
        )

        ET.SubElement(
            none,
            tag("CopyToOutputDirectory"),
        ).text = "Always"

        # ---------------------------------------------------------
        # Save
        # ---------------------------------------------------------

        ET.indent(tree, space="\t")
        with open(project_path, "wb") as f:
            tree.write(f, encoding="utf-8", xml_declaration=True)
        self.signal_log_message(
            f"  Project updated successfully: {project_path.name}"
        )

    from pathlib import Path

    LOG_COLORS = {
        "normal": "#D4D4D4",  # Light grey
        "info": "#61AFEF",  # Blue
        "success": "#98C379",  # Green
        "warning": "#E5C07B",  # Yellow/orange
        "error": "#E06C75",  # Red
        "debug": "#C678DD",  # Purple
    }

    def move_project_to_archive(
            self,
            project_path: Path,
            destination_dir: Path,
    ) -> None:
        """Move a decompiled project to the archive, flattening 584E07D1."""

        project_dir = Path(project_path).parent
        destination_dir = Path(destination_dir)
        destination_dir.mkdir(parents=True, exist_ok=True)

        def move_tree(source_dir: Path, target_dir: Path) -> None:
            for source in list(source_dir.iterdir()):
                if source.is_dir() and source.name == "584E07D1":
                    for child in list(source.iterdir()):
                        shutil.move(str(child), str(destination_dir / child.name))
                    source.rmdir()
                    continue

                target = target_dir / source.name

                if source.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    move_tree(source, target)

                    if not any(source.iterdir()):
                        source.rmdir()
                else:
                    shutil.move(str(source), str(target))

        self.signal_log_message(
            f"Moving project files\n"
            f"  Source:      {project_dir}\n"
            f"  Destination: {destination_dir}"
        )

        try:
            move_tree(project_dir, destination_dir)

            if not list(destination_dir.rglob("*.csproj")):
                self.signal_log_message("ERROR: No .csproj found in destination.")
                return

            if list(destination_dir.rglob("584E07D1")):
                self.signal_log_message("WARNING: 584E07D1 still exists.")
            else:
                self.signal_log_message("Verified: 584E07D1 completely flattened.")

            self.signal_log_message(f"Project moved successfully: {destination_dir}")

        except OSError as exc:
            self.signal_log_message(f"ERROR moving project files: {exc}")

    def add_project_to_solution(self, solution_path: Path, project_path: Path, game=None,
                                add_to_solution_archive_folder=False, move_decompiled_project=False, ) -> bool:

        solution_path = Path(solution_path).resolve()
        project_path = Path(project_path).resolve()
        original_project_path = project_path
        self.signal_log_message(f"Adding project to solution: {project_path.name}")

        if not solution_path.exists():
            self.signal_log_message(f"Solution not found: {solution_path}")
            return False

        if not project_path.exists():
            self.signal_log_message(f"Project not found: {project_path}")
            return False

        # ---------------------------------------------------------
        # Destination
        # ---------------------------------------------------------

        archive_dir = solution_path.parent / "indie-game-archive"
        archive_dir.mkdir(parents=True, exist_ok=True)

        project_dir = project_path.parent
        destination_dir = archive_dir / project_dir.name

        if add_to_solution_archive_folder and game is not None:
            game.archived = destination_dir

        self.signal_log_message(f"  Source:      {project_dir}")
        self.signal_log_message(f"  Destination: {destination_dir}")

        # ---------------------------------------------------------
        # Move Project
        # ---------------------------------------------------------

        # ---------------------------------------------------------
        # Project path
        # ---------------------------------------------------------

        try:
            project_path_value = os.path.relpath(
                project_path,
                solution_path.parent,
            ).replace("\\", "/")

            original_project_path_value = os.path.relpath(
                original_project_path,
                solution_path.parent,
            ).replace("\\", "/")

        except ValueError:
            project_path_value = project_path.as_posix()
            original_project_path_value = original_project_path.as_posix()

            self.signal_log_message("Project is on a different drive.")

        self.signal_log_message(f"Solution path: {solution_path}")
        self.signal_log_message(f"Project path: {project_path_value}")

        # ---------------------------------------------------------
        # Parse solution
        # ---------------------------------------------------------

        try:
            tree = ET.parse(solution_path)
        except ET.ParseError as exc:
            self.signal_log_message(f"ERROR reading solution: {exc}")
            return False

        root = tree.getroot()

        for parent in root.iter():
            for project in list(parent):
                if project.tag != "Project":
                    continue

                path = project.get("Path")

                if path == original_project_path_value:
                    parent.remove(project)
                    self.signal_log_message(f"  Removed old project entry: {path}")

                elif path == project_path_value:
                    parent.remove(project)
                    self.signal_log_message(f"  Removed existing project entry: {path}")

        # ---------------------------------------------------------
        # Find / create solution folder
        # ---------------------------------------------------------

        folder_name = (
            "/indie-game-archive/"
            if add_to_solution_archive_folder
            else "/Reference-Projects/"
        )

        folder = next(
            (
                element
                for element in root.findall("Folder")
                if element.get("Name") == folder_name
            ),
            None,
        )

        if folder is None:
            folder = ET.SubElement(
                root,
                "Folder",
                {"Name": folder_name},
            )

            self.signal_log_message(
                f"  Created {folder_name} solution folder."
            )

        # ---------------------------------------------------------
        # Remove existing project entry
        # ---------------------------------------------------------

        project_name = project_path.stem.casefold()

        for parent in root.iter("Folder"):
            for project in list(parent.findall("Project")):
                path = project.get("Path")
                if not path:
                    continue

                existing_name = Path(path).stem.casefold()

                if (
                        existing_name == project_name
                        and parent.get("Name") == folder_name
                ):
                    parent.remove(project)
                    self.signal_log_message(
                        f"  Removed existing project entry: {path}"
                    )

        # ---------------------------------------------------------
        # Add project
        # ---------------------------------------------------------

        ET.SubElement(folder, "Project", {"Path": project_path_value}, )

        self.signal_log_message(f"Added {project_path.name} to {folder_name}")

        # ---------------------------------------------------------
        # Save
        # ---------------------------------------------------------

        ET.indent(tree, space="  ")

        try:
            tree.write(
                solution_path,
                encoding="utf-8",
                xml_declaration=True,
            )
        except OSError as exc:
            self.signal_log_message(f"ERROR saving solution: {exc}")
            return False

        self.signal_log_message("  Solution updated successfully.")

        return True

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


def run_in_background(func, *args):
    threading.Thread(
        target=func,
        args=args,
        daemon=True,
    ).start()


def _decompress_games(game: XBLIGGame, log):
    if game.extracted is None or not game.package:
        return game
    root = game.extracted / "584E07D1"
    archive = root / "Content.7z"
    try:
        log(f"Decompressing {game.title}: {archive} folder(s)", "success")
        decompress_content(archive, root, log_callback=log, delete_archive=True)
    except Exception as e:
        log(f"Failed to decompress {game.title}: {type(e).__name__}: {e}", "success")
    return game


CONTENT_EXTENSIONS = {
    ".xnb", ".xgs", ".xap",
    ".wav", ".mp3", ".wma",
    ".png", ".jpg", ".jpeg", ".dds", ".xml", ".txscene"
}


def _compress_games(game: XBLIGGame, log):
    if game.extracted is None or not game.package:
        return game

    root = game.extracted / "584E07D1"
    archive = root / "Content.7z"

    if archive.exists():
        log(f"Archive already exists: {archive} Decompress.", "success")
        return archive
    files = [
        p
        for p in root.rglob("*")
        if p.is_file()
           and len(p.relative_to(root).parts) > 1
           and p.suffix.lower() in CONTENT_EXTENSIONS
    ]
    folders = list({p.parent for p in files})

    if not folders:
        log(f"No content files found for {game.title}: {root}", "success")
        return game

    content_folders = list({p.parent for p in files})
    # content_folders = [
    #     p for p in folders
    #     if not any(parent in folders for parent in p.parents)
    # ]

    try:
        log(f"Compressing {len(folders)} {game.title} Content Folders", "success")
        compress_folders(root, content_folders, archive, True, log_callback=log)
        log(f"Compressed {game.title} successfully", "success")
    except Exception as e:
        log(f"Failed to compress {game.title}: {type(e).__name__}: {e}", "success")
    return game


class CompressWorker(QObject):
    log = Signal(str, str)
    finished = Signal()

    def __init__(self, function: Callable[..., None], *args, **kwargs, ):
        super().__init__()
        self.function = function
        self.args = args
        self.kwargs = kwargs

    @Slot()
    def run(self):
        # with redirect_stdout(QtLogger(self.log.emit)):
        self.kwargs["log"] = self.log.emit
        self.function(*self.args, **self.kwargs)
        self.finished.emit()


class ScanWorker(QObject):
    finished_signal = Signal(list)
    log_signal = Signal(str, str, bool)
    progress_signal = Signal(int, int)
    total_files_signal = Signal(int)

    def __init__(self, force: bool = False):
        super().__init__()
        self.options = None
        self.games = None
        self._rainbow_index = 1

        self.converter = ConvertXnaProjects(get_app_dir(), self.games, self.options)
        self.converter.log_signal.connect(self.log_signal.emit)
        self.converter.progress_signal.connect(self.progress_signal.emit)
        self.converter.finished_signal.connect(self.finished_signal.emit)
        self.converter.total_files_signal.connect(self.total_files_signal.emit)

        self.total_files = 0
        self.config = load_config()
        self.force = force

    def _set_total_files(self, total: int):
        self.total_files = total
        self.total_files_signal.emit(total)
        # Forward converter signals
        # self.converter.log_signal.connect(self.log_signal)
        # self.converter.progress_signal.connect(self.progress_signal)

    def signal_log_message(self, message, color=None, clear=False):
        if color is None:
            color = RAINBOW_COLORS[self._rainbow_index]
            self._rainbow_index = (self._rainbow_index + 1) % len(RAINBOW_COLORS)
        self.log_signal.emit(message, color, clear)

    @Slot()
    def run(self):
        try:
            games: list[XBLIGGame] = []
            # current_mtime = get_folder_mtime(root)
            cache = None if self.force else load_cache()

            if cache is not None:
                self.signal_log_message("Checking game cache...")
                games = cache["games"]
                self.signal_log_message(f"Loaded {len(games)} games from cache.")
                self.total_files_signal.emit(100)
            else:
                self.signal_log_message("Scanning folders...")
                solution_path = Path(self.config["indie-game-solution-location"])
                downloads_path = (Path(self.config["indie_games_path"]))
                archive_path = (solution_path.parent / "indie-game-archive")
                if not solution_path.exists():
                    self.signal_log_message(f"Folder {solution_path} does not exist.")
                    self.total_files_signal.emit(0)
                    self.finished_signal.emit(games)
                    return
                # ---------------------------------------------
                # Scan original XBLIG downloads/content
                # ---------------------------------------------

                game_paths = [downloads_path, archive_path]
                _ = self.converter.extract_packages(game_paths)
                games = self.converter.find_packages(game_paths)
                self.signal_log_message(f"Found {len(games)} games.")

                save_cache(games)

                self.signal_log_message(f"Cache updated: {len(games)} games.")

            self.finished_signal.emit(games)

        except Exception as exc:
            self.signal_log_message(
                f"Game scan failed: {exc}",
                "error",
            )
            raise


from PySide6.QtWidgets import QStyledItemDelegate
from PySide6.QtCore import QRect, QSize, Qt


class IconButtonDelegate(QStyledItemDelegate):

    def paint(self, painter, option, index):

        icon = index.data(Qt.ItemDataRole.DecorationRole)
        game = index.data(Qt.ItemDataRole.UserRole)

        if not icon:
            return

        painter.save()

        # Button rectangle
        button_rect = option.rect.adjusted(
            2, 2, -2, -2
        )

        # Draw button background/border
        painter.setPen(Qt.GlobalColor.gray)

        painter.drawRoundedRect(
            button_rect,
            6,
            6,
        )

        # Draw icon
        icon_size = 32

        icon_rect = QRect(
            button_rect.center().x() - icon_size // 2,
            button_rect.center().y() - icon_size // 2,
            icon_size,
            icon_size,
        )

        icon.paint(
            painter,
            icon_rect,
            Qt.AlignmentFlag.AlignCenter,
        )

        painter.restore()

    def editorEvent(
            self,
            event: QEvent,
            model,
            option,
            index,
    ):
        if event.type() == QEvent.Type.MouseButtonRelease:
            mouse_event = cast(QMouseEvent, event)

            if mouse_event.button() == Qt.MouseButton.LeftButton:
                game = index.data(Qt.ItemDataRole.UserRole)

                if game:
                    print(f"Launch {game.title}")

                return True

        return super().editorEvent(
            event,
            model,
            option,
            index,
        )


def folder_status(game: XBLIGGame, moving=False) -> tuple[bool, bool, Path, list[Path]]:
    cs_proj_files_extracted = []
    game_folder = Path()
    config = load_config()
    extracted_state = bool(
        game.extracted and game.extracted.exists() and any(p.is_file() for p in game.extracted.rglob("*")))
    archived_state = bool(game.archived is not None and game.archived.exists() and any(
        p.is_file() for p in game.archived.rglob("*")))
    folder = Path(config["indie_games_path"])
    solution_folder = Path(config["indie-game-solution-location"]).parent / "indie-game-archive"
    if archived_state or moving:
        game_folder = solution_folder / game.title
        game.archived = game_folder
    elif extracted_state:
        game_folder = folder / game.extracted
        game.extracted = game_folder

    game.dll_files = list(game_folder.rglob("*.dll"))
    game.executables = list(game_folder.rglob("*.exe"))
    cs_proj_files_extracted = list(game_folder.rglob("*.csproj"))
    return archived_state, extracted_state, game_folder, cs_proj_files_extracted


def run_powershell_script(game: XBLIGGame | None, script=1, log_message=None, config=None):
    def log_message_callback(message, color=None):
        if log_message is not None:
            log_message(message, color)

    if script == 1:
        script = get_app_dir() / "scripts" / "build_projects_clean.ps1"
        root = Path(config["indie-game-solution-location"]).parent
        args = [
            "powershell.exe",
            "-ExecutionPolicy", "Bypass",
            "-File", str(script),
            "-Root", str(root),
        ]

        if game is not None:
            args.extend([
                "-Folder", str(game.folder_title),
                "-Game",
            ])
        process = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            log_message_callback(line.rstrip())

        process.wait()

        if process.returncode != 0:
            log_message_callback(f"PowerShell exited with code {process.returncode}")
    if script == 2:
        script = get_app_dir() / "scripts" / "Extract-STFS.ps1"
        process = subprocess.Popen(
            [
                "powershell.exe",
                "-ExecutionPolicy", "Bypass",
                "-File", str(script),
                "-Path", str(game.package),
                "-OutputDir", str(game.extracted),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            log_message_callback(line.rstrip())

        process.wait()

        if process.returncode != 0:
            log_message_callback(f"PowerShell exited with code {process.returncode}")


class XBLIGDialog(QDialog):

    def paintEvent(self, event):
        painter = QPainter(self)

        painter.drawPixmap(
            self.rect(),
            self.background.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            ),
        )
        super().paintEvent(event)

    def moby_games_lookup(self):
        config = load_config()

        mobygames = MobyGamesClient(
            api_key=config.mobygames_api_key,
            cache_file=Path("config/mobygames-cache.json"),
        )

        for game in self.games:
            if not game.publisher:
                game.publisher = mobygames.get_publisher(
                    game.title
                )

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

    def total_files_progress(self, total_files: int):
        self.progress_bar.setRange(0, total_files)

    def tool_finished(self, result: ConversionResult):
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        # todo: copy log files when xnb-extractor has run
        if result.tool == "xnb_extractor":
            source = xnb_extractor.parent / "logs"
            destination = get_app_dir() / "logs"
            if source.exists():
                shutil.copytree(source, destination, dirs_exist_ok=True)
        cleanup_tool("conversion", None)
        self.validate1_btn.setDisabled(False)
        self.validate2_btn.setDisabled(False)
        self.validate3_btn.setDisabled(False)

        if result.success:
            self.log_message(
                f"{result.tool}: SUCCESS - "
                f"{len(result.output_files)} files created."
            )
        else:
            self.log_message(
                f"{result.tool}: FAILED"
            )

            if result.error:
                self.log_message(result.error)

            if result.stderr:
                self.log_message(result.stderr)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.games: list[XBLIGGame] = []
        self.options = None

        self.converter = ConvertXnaProjects(get_app_dir(), self.games, self.options)
        self.converter.log_signal.connect(self.log_message)
        self.converter.progress_signal.connect(self.update_scan_progress)
        self.converter.finished_signal.connect(self.tool_finished)
        self.converter.total_files_signal.connect(self.total_files_progress)

        self.background = QPixmap(get_app_dir() / "assets/images/img.png")

        self._ilspy_queue = None
        self.ilspy_process = None
        self._rainbow_index = 1
        self.conn = None
        self.scan_worker = None
        self.scan_thread = None
        self.config = load_config()
        self.columns = None
        self.game = None
        self.extracted = None
        self.overwrite_check = QCheckBox()
        self.compress_worker: CompressWorker | None = None
        self.worker = None
        self.compress_thread = None
        self.decompress_btn = None
        # self.all_checkbox = None
        self.drawer_open = False
        self._last_mtime = None
        self._cache = None
        self.compress_btn = None
        self.setWindowTitle(
            f"XBLIG Rebuilder {self.config["game_manager_version"]}"
        )
        self.resize(1100, 750)

        db = Database()
        self.db = db

        self.build_ui()
        self.load_games(self.games)
        self.create_settings_drawer()
        self.apply_style()

    def print_games(self):
        for i, game in enumerate(self.games, 1):
            print("=" * 80)
            print(f"Game #{i}")
            print("=" * 80)

            for key, value in vars(game).items():
                label = key.replace("_", " ").title()
                print(f"{label:<20}: {value}")

            print()

    def get_selected_games(
            self,
    ) -> tuple[list[XBLIGGame], list[QModelIndex]] | None:

        indexes = self.game_table.selectionModel().selectedRows()

        if not indexes:
            return None

        games = [
            self.model.get_game_from_index(index)
            for index in indexes
        ]

        return games, indexes

    def get_random_games(self):
        random.seed(time.time())
        random.shuffle(self.games)
        random_project = self.games[0]
        return random_project

    # def convert_selected_folders(self):
    #     if (result := self.get_selected_game()) is None:
    #         return
    #     game, indexes = result
    #
    #     if not game:
    #         return
    #
    #     decompiled = game.decompiled
    #
    #     if decompiled is None:
    #         QMessageBox.warning(
    #             self,
    #             "Not Decompiled",
    #             "Please decompile the game first."
    #         )
    #         return
    #
    #     converter = self.method_name()
    #
    #     converter.convert_project_folder(decompiled)

    def update_progress(self, value: int):
        self.progress_bar.setValue(value)
        self.progress_bar.setFormat(
            f"Scanner {value}%"
        )

    # def convert_game_project(self):
    #     if (result := self.get_selected_game()) is None:
    #         return
    #     game, _ = result
    #     converter = self.method_name()
    #     projects = get_cs_project_folders(game, self.log_message)
    #     self.log_message(f"Found {len(projects)} projects")
    #     for project in projects:
    #         try:
    #             converter.convert_project_folder(project)
    #         except Exception as e:
    #             self.log_message(
    #                 f"FAILED {project}: {e}"
    #             )

    def convert_content(self, tool_id=1):
        self.validate1_btn.setDisabled(True)
        self.validate2_btn.setDisabled(True)
        self.validate3_btn.setDisabled(True)
        if (result := self.get_selected_games()) is None:
            return
        games, indexes = result
        for game in games:
            if game:
                ensure_tool_extracted("conversion", None)
                self.progress_bar.setRange(0, 0)  # Busy animation
                run_in_background(self.converter.convert_xnb_folder_tools, game, tool_id)

    def tool_finished(self, result: ConversionResult):
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        # todo: copy log files when xnb-extractor has run
        if result.tool == "xnb_extractor":
            source = xnb_extractor.parent / "logs"
            destination = get_app_dir() / "logs"
            if source.exists():
                shutil.copytree(source, destination, dirs_exist_ok=True)
        cleanup_tool("conversion", None)
        self.validate1_btn.setDisabled(False)
        self.validate2_btn.setDisabled(False)
        self.validate3_btn.setDisabled(False)

        if result.success:
            self.log_message(
                f"{result.tool}: SUCCESS - "
                f"{len(result.output_files)} files created."
            )
        else:
            self.log_message(
                f"{result.tool}: FAILED"
            )

            if result.error:
                self.log_message(result.error)

            if result.stderr:
                self.log_message(result.stderr)

    def decompile_project(self, game: XBLIGGame, parent, use_gui: bool, output_dir: Path, include_dlls=False) -> Path:
        ensure_tool_extracted("ilspy" if use_gui else "ilspycmd", None, )
        ilspy_exe = ILSPY_GUI if use_gui else ILSPY_CMD

        # ---------------------------------------------------------
        # Build decompilation queue
        # ---------------------------------------------------------

        if include_dlls:
            targets = [(executable, True) for executable in game.executables] + [(dll, False) for dll in game.dll_files]
        else:
            targets = [(executable, True) for executable in game.executables]

        if not targets:
            self.log_message("No executables or DLLs found to decompile.")
            return output_dir

        self.log_message(f"Output Folder: {output_dir}")
        self.log_message(f"ILSpy Executable: {ilspy_exe}")

        # Keep the queue/process alive for the duration of the operation.
        self._ilspy_queue = targets
        self._ilspy_process = None
        self._ilspy_project_dir = output_dir
        self._ilspy_game = game
        self._ilspy_output_dir = output_dir
        self._ilspy_exe = ilspy_exe
        self._ilspy_use_gui = use_gui

        self._start_next_decompile(parent)

        return output_dir

    def _start_next_decompile(self, parent=None):
        """Start the next item in the ILSpy decompilation queue."""

        if not self._ilspy_queue:
            self.log_message("All ILSpy decompilation jobs completed.")
            self._ilspy_process = None
            return

        target, is_executable = self._ilspy_queue.pop(0)

        output_dir = self._ilspy_output_dir
        ilspy_exe = self._ilspy_exe
        use_gui = self._ilspy_use_gui
        game = self._ilspy_game

        if use_gui:
            arguments = [str(target)]
        else:
            arguments = ["-p", "-o", str(output_dir), ]
            if is_executable:
                arguments.extend(["-r", str(target.parent), ])
            arguments.extend(["--nested-directories", str(target), ])

        process = QProcess(parent)
        self._ilspy_process = process

        process.setProgram(str(ilspy_exe))
        process.setArguments(arguments)
        process.setWorkingDirectory(str(output_dir))

        self.log_message(f"Command: {ilspy_exe} {' '.join(arguments)}")
        self.log_message(f"Working directory: {process.workingDirectory()}")

        if not use_gui:
            process.readyReadStandardOutput.connect(
                lambda: self._log_process_output(process)
            )
            process.readyReadStandardError.connect(
                lambda: self._log_process_output(process)
            )

        process.errorOccurred.connect(
            lambda error, target=target:
            self.log_message(f"ILSpy process error ({target.name}): {error}")
        )

        process.started.connect(
            lambda target=target:
            self.log_message(f"ILSpy started: {target.name}")
        )

        process.finished.connect(
            lambda exit_code, exit_status, target=target:
            self._decompile_process_finished(target, exit_code, exit_status, )
        )

        self.log_message(f"Starting ILSpy: {target.name}")

        process.start()

    def _log_process_output(self, process: QProcess) -> None:
        for data in (
                process.readAllStandardOutput(),
                process.readAllStandardError(),
        ):
            text = bytes(data.data()).decode(
                "utf-8",
                errors="replace",
            ).rstrip()

            if text:
                self.log_message(text)

    def _decompile_process_finished(
            self,
            target,
            exit_code,
            exit_status,
    ):
        self.log_message(
            f"ILSpy finished: {target.name} "
            f"(exit code: {exit_code})"
        )

        self.on_decompile_finished(
            self._ilspy_project_dir,
            self._ilspy_game,
            exit_code,
            exit_status,
        )

        self._ilspy_process = None

        self._start_next_decompile()

    def on_decompile_finished(self, project_dir, game, exit_code, exit_status):
        self.log_message(f"ILSpy finished: exit code={exit_code}, status={exit_status}")

        if exit_code != 0:
            self.log_message(f"ILSpy failed while decompiling {game.title}")
            return

        profile_string = (
                project_dir / "Microsoft.Xna.Framework.RuntimeProfile"
        )

        if profile_string.exists():
            game.content_format = profile_string.read_text().strip()
        else:
            game.content_format = ""

        game.decompiled = project_dir

        self.log_message(f"Decompiled project: {project_dir}")

        # if open_explorer:
        #     subprocess.Popen(["explorer", str(project_dir)])

    def update_scan_progress(self, current: int, total: int):
        value = int(current * 100 / total) if total else 0
        self.progress_bar.setValue(value)
        self.progress_bar.setFormat(f"Scanner {current:,}")

    def rescan_games_responsive(self, force=False):

        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Scanner 0")
        self.scan_btn.setEnabled(False)

        if self.cache_check.isChecked():
            force = True

        thread = QThread(self)
        self.scan_thread = thread
        self.scan_worker = ScanWorker(force=force)
        self.scan_worker.moveToThread(self.scan_thread)

        thread.started.connect(self.scan_worker.run)
        self.scan_worker.log_signal.connect(self.log_message)
        self.scan_worker.progress_signal.connect(self.update_scan_progress)
        self.scan_worker.finished_signal.connect(self.scan_finished)

        self.scan_worker.finished_signal.connect(self.scan_thread.quit)
        self.scan_worker.finished_signal.connect(self.scan_worker.deleteLater)
        thread.finished.connect(self.scan_thread.deleteLater)

        self.scan_thread.start()

    def scan_finished(self, games):
        self.games = games
        self.load_games(self.games)
        self.scan_btn.setEnabled(True)

    # def log_message(self, message):
    #     self.log_message(message, "#2ecc71")

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
        index = self.game_table.currentIndex()
        if not index.isValid():
            return

        game = index.data(Qt.ItemDataRole.UserRole)
        if game is None:
            return

        self.drawer_update_labels(game)
        self.show_settings_drawer()

    def drawer_update_labels(self, game: XBLIGGame):
        self.title_lbl.setText(game.title)
        self.titleid_lbl.setText(game.title_id or "-")
        self.dll_files_lbl.setText("\n".join(str(dll) for dll in game.dll_files) if game.dll_files else "-")

        if game.executables:
            self.exe_lbl.setText(
                "\n".join(str(executable) for executable in game.executables) if game.executables else "-")
        else:
            self.exe_lbl.setText("-")

        if game.xml:
            self.xml_lbl.setText(str(game.xml))
        else:
            self.xml_lbl.setText("-")

        if game.extracted is not None:
            content_dir = game.extracted / "584E07D1" / "Content"
            output_dir = content_dir.parent / "Content_Output"
            self.input_folder.setText(str(content_dir))
            self.output_folder.setText(str(output_dir))
        else:
            self.input_folder.setText(str("-"))
            self.output_folder.setText(str("-"))

        # if game.decompiled:
        #     self.decompiled_lbl.setText(str(game.decompiled))
        # else:
        #     self.decompiled_lbl.setText("-")
        if game.extracted:
            self.extracted_lbl.setText(str(game.extracted))
        else:
            self.extracted_lbl.setText("-")
        if game.archived:
            self.archived_lbl.setText(str(game.archived))
        else:
            self.archived_lbl.setText("-")

        if game.folder_title:
            self.title_root_lbl.setText(game.folder_title)
        else:
            self.title_root_lbl.setText("-")

    def compress_decompress_extracted_content(self, compress: bool):
        result = self.get_selected_games()
        if not result:
            return
        games, _ = result
        for game in games:
            if compress:
                self.log_message(f"Compressing Game {game.title}")
                func = partial(_compress_games, game)
            else:
                func = partial(_decompress_games, game)
            self.game = game
            self.run_worker(func)

    def run_worker(self, func: Callable[..., None] | Callable[..., None]):
        thread = QThread(self)
        self.compress_thread = thread
        worker = CompressWorker(func)
        self.compress_worker = worker
        worker.log.connect(self.log_message)
        worker.finished.connect(self.compress_thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._worker_finished)

        worker.moveToThread(self.compress_thread)
        thread.started.connect(worker.run)
        self.compress_thread.start()

    def _worker_finished(self) -> None:
        # self.game.extracted = self.extracted
        # self.game.executables = list(self.extracted.rglob("*.exe"))

        save_cache(self.games)
        self.load_games(self.games)

    def extract_game_package(self):
        overwrite = self.overwrite_check.isChecked()
        if (result := self.get_selected_games()) is None:
            self.log_message(f"No game selected.")
            return
        games, _ = result
        for game in games:
            self.log_message(f"Extracting Game {game.title} Package", clear_console=True)
            if not game.package:
                self.log_message(f"{game.title} has no package.")
                return
            # if not overwrite and self.game.extracted is not None:
            #     self.log_message(f"{self.game.title} Already Extracted")
            #     return
            try:
                extracted = self.converter.extract_package(game, False, overwrite=overwrite)
                # game.extracted = extracted
                # game.executables = list(extracted.rglob("*.exe"))
                archived_state, extracted_state, game_folder_status, cs_proj_files_extracted = folder_status(game)
                self.log_message(f"Extracted {game.title} successfully")
                save_cache(self.games)
                self.drawer_update_labels(game)

            except Exception as e:
                self.log_message(f"Error extracting {game.title}: {type(e).__name__}: {e}")
            self.load_games(self.games, refresh_only=True)

    def load_games(self, games: list[XBLIGGame], refresh_only: bool = False, ):
        for game in games:
            metadata = self.db.get_xblig_metadata(game.title)

            if metadata:
                game.publisher = (
                        metadata["developer_account"]
                        or metadata["developer"]
                )

        if refresh_only:
            header = self.game_table.horizontalHeader()

            sort_column = header.sortIndicatorSection()
            sort_order = header.sortIndicatorOrder()

            self.model.beginResetModel()
            self.model.games = list(games)
            self.model.endResetModel()

            if sort_column >= 0:
                self.model.sort(sort_column, sort_order)

        else:
            self.model.set_games(games)

        game_source: GameSource = "indie"

        self.db.import_games_from_source(
            game_source,
            indie_game_list=games,
            log_callback=self.log_message,
        )

        self.game_table.setIconSize(QSize(32, 32))
        self.game_table.verticalHeader().setVisible(False)
        self.game_table.verticalHeader().setDefaultSectionSize(40)

    from PySide6.QtWidgets import (QDialog, )

    class BuildSelectedDialog(QDialog):
        def __init__(self, parent=None):
            super().__init__(parent)

            self.setWindowTitle("Build Selected Game")
            self.resize(420, 280)

            layout = QVBoxLayout(self)

            # Build options
            options_group = QGroupBox("Build Options")
            options_layout = QVBoxLayout(options_group)

            # self.config = load_config_file()
            # solution_location = self.config["indie-game-solution-location"]
            #
            # self.solution_file = QLineEdit()
            # self.solution_file.setText(solution_location)
            # self.solution_file.setMinimumHeight(28)
            # Decompile
            self.decompile_check = QCheckBox("Decompile executable")
            self.decompile_check.setChecked(True)
            options_layout.addWidget(self.decompile_check)

            # Decompile sub-options
            decompile_layout = QVBoxLayout()
            decompile_layout.setContentsMargins(24, 0, 0, 0)

            self.decompile_cli = QRadioButton("Use ILSpy command line")
            self.decompile_gui = QRadioButton("Use ILSpy GUI")

            self.decompile_cli.setChecked(True)

            group = QButtonGroup(self)
            group.addButton(self.decompile_cli)
            group.addButton(self.decompile_gui)

            decompile_layout.addWidget(self.decompile_cli)
            decompile_layout.addWidget(self.decompile_gui)

            options_layout.addLayout(decompile_layout)

            self.convert_csproj_check = QCheckBox("Convert Games's .csproj File or Files.")
            self.convert_content_check = QCheckBox("Convert Games's Content Files with Default Converter.")
            self.add_to_solution_check = QCheckBox("Add To Indie Game Solution")
            self.open_vs_check = QCheckBox("Open Indie Game Solution in Visual Studio.")
            self.open_explorer_check = QCheckBox("Open Decompiled Project Folder.")
            self.archive_project_check = QCheckBox("Archive Project to Indie Game Solution")
            self.convert_csproj_check.setChecked(True)
            self.convert_content_check.setChecked(True)

            self.decompile_check.toggled.connect(self.decompile_cli.setEnabled)
            self.decompile_check.toggled.connect(self.decompile_gui.setEnabled)

            self.decompile_cli.setEnabled(True)
            self.decompile_gui.setEnabled(True)

            # options_layout.addWidget(self.solution_file)
            options_layout.addWidget(self.convert_csproj_check)
            options_layout.addWidget(self.archive_project_check)
            options_layout.addWidget(self.convert_content_check)
            options_layout.addWidget(self.add_to_solution_check)
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
            return {
                "decompile": self.decompile_check.isChecked(),
                "decompile_gui": self.decompile_gui.isChecked(),
                "convert_csproj": self.convert_csproj_check.isChecked(),
                "add_to_solution": self.add_to_solution_check.isChecked(),
                "convert_content": self.convert_content_check.isChecked(),
                "archive_project": self.archive_project_check.isChecked(),
                "open_visual_studio": self.open_vs_check.isChecked(),
                "open_explorer": self.open_explorer_check.isChecked(),
            }

    def decompile(self) -> None:
        if (result := self.get_selected_games()) is None:
            return
        games, indexes = result

        for game in games:

            dlg = self.BuildSelectedDialog()
            if not dlg.exec(): return
            options = dlg.options()
            if game.extracted is None:
                self.log_message(f"Skipping {game.title} because it has not been extracted")
                continue
            content_dir = game.extracted
            if options["decompile"]:
                archived_state, extracted_state, game_folder_status, cs_proj_files = folder_status(game, moving=False)
                self.log_message(f"Decompiling {game.title} at {content_dir}", clear_console=True)
                self.decompiler(game, content_dir, options)

            if options["archive_project"]:
                archived_state, extracted_state, game_folder_status, cs_proj_files = folder_status(game, moving=True)
                destination_dir = game_folder_status
                for csproj_file in cs_proj_files:
                    self.log_message(f"Processing: {csproj_file}")

                    self.converter.move_project_to_archive(csproj_file, destination_dir)
                    self.log_message(f"Project Moved: {csproj_file} -> {destination_dir}")

            if options["convert_csproj"]:
                solution_path = Path(self.config["indie-game-solution-location"])
                archived_state, extracted_state, game_folder_status, cs_proj_files = folder_status(game, moving=False)
                if len(cs_proj_files) != 0:
                    self.log_message(f"Found {len(cs_proj_files)} csproj files in {game_folder_status}")
                    if game_folder_status is None:
                        raise ValueError("Game has not been extracted")

                    for csproj_file in cs_proj_files:
                        try:
                            if game.folder_title is not None and (game.title.lower() in csproj_file.stem.lower() or any(
                                    csproj_file.stem.lower() == executable1.stem.lower() for executable1 in
                                    game.executables)):
                                new_csproj_file = csproj_file.with_name(f"{game.folder_title}.csproj")
                                try:
                                    if not new_csproj_file.exists():
                                        csproj_file.rename(new_csproj_file)
                                        self.log_message(
                                            f"Renamed project: {csproj_file.name} -> {new_csproj_file.name}")
                                        csproj_file = new_csproj_file
                                except OSError as e1:
                                    self.log_message(f"  ERROR renaming {csproj_file}: {e1}")
                            self.converter.clean_csproj(csproj_file, game.dll_files, game, game.resx_files)
                        except Exception as e:
                            self.log_message(f"Failed to Convert: {csproj_file}: {e}")

            if options["add_to_solution"]:
                solution_path = Path(self.config["indie-game-solution-location"])
                archived_state, extracted_state, game_folder_status, cs_proj_files = folder_status(game, moving=False)
                if len(cs_proj_files) != 0:
                    self.log_message(f"Found {len(cs_proj_files)} csproj files in {game_folder_status}")
                    if game_folder_status is None:
                        raise ValueError("Game has not been extracted")
                    for csproj_file in cs_proj_files:
                        add_to_archive = (game.folder_title is not None and (
                                game.title.lower() in csproj_file.stem.lower() or any(
                            csproj_file.stem.lower() == executable.stem.lower() for executable in game.executables)))
                        try:
                            self.converter.add_project_to_solution(solution_path, csproj_file, game,
                                                                   add_to_solution_archive_folder=add_to_archive,
                                                                   move_decompiled_project=options["archive_project"])
                        except Exception as e:
                            self.log_message(f"Failed to Add Project to Solution {e}")

            if options["open_visual_studio"]:
                self.log_message("Opening Solution in Visual Studio. The Decompiled Projects Should Have Been Added.")
                solution = self.config["indie-game-solution-location"]
                os.startfile(solution)

            # folder = game.extracted
            # content_dir = folder / "584E07D1" / "Content"
            # assert game.decompiled is not None
            # copy_content_folder(content_dir, game.decompiled / "Content")
            t = ToolManager()
            t.cleanup()

    def decompiler(self, game: XBLIGGame, game_folder: Path | None, options: dict[str, bool]):
        if game_folder:
            assert game.folder_title is not None
            folder_title = game.folder_title
            self.log_message(f"Decompiling {folder_title} to {game_folder}", clear_console=True)
            try:
                decompiled = self.decompile_project(game, parent=self, use_gui=options["decompile_gui"],
                                                    output_dir=game_folder, include_dlls=True)
            except Exception as e:
                self.log_message(f"Failed to Decompile: {game.title}: {e}")

    def launch_selected(self):
        self.log_message("Launching selected game...")

    def refresh_games(self):
        self.load_games(self.games)

    def open_selected_folder(self, folder="root"):
        if (result := self.get_selected_games()) is None:
            return
        games, index = result
        for game in games:
            if folder == "root":
                if not game or not game.game_root or not game.game_root.exists():
                    self.log_message("No valid game folder selected.")
                    return

                subprocess.Popen(["explorer", str(game.game_root)])
                self.log_message(f"Opened: {game.game_root}")
            if folder == "extracted":
                if not game or not game.extracted or not game.extracted.exists():
                    self.log_message("Game has not been extracted.", "#f1c40f")
                    return

                subprocess.Popen(["explorer", str(game.extracted)])
                self.log_message(f"Opened: {game.extracted}", "#2ecc71")

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

    def delete_game_files(self, files: str):
        if (result := self.get_selected_games()) is None:
            return
        games, indexes = result
        for game in games:
            if game is None or game.title_id is None:
                return

            attrs = {
                "decompiled": (
                    "decompiled",
                    Path("d/downloads") / "decompiled" / game.title,
                    game.archived,
                ),
                "extracted": (
                    "extracted",
                    Path("d/downloads") / "extracted" / game.title,
                    game.extracted,
                ),
            }

            try:
                if files == "bin-obj":
                    if game.archived is None:
                        self.log_message("Game has not been archived.")
                        return
                    self.log_message("Removing Bin and Obj")
                    if self.overwrite_check.isChecked():
                        run_powershell_script(game, 1, log_message=self.log_message, config=self.config)
                    else:
                        run_powershell_script(None, 1, log_message=self.log_message, config=self.config)
                else:
                    try:
                        attr_name, path, attr_path_value = attrs[files]
                        if path is not None and path.exists():
                            shutil.rmtree(path)
                            self.log_message(f"Deleted: {path}")
                            setattr(game, str(attr_name), None)
                        elif attr_path_value and attr_path_value.exists():
                            shutil.rmtree(attr_path_value)
                            self.log_message(f"Deleted: {attr_path_value}")
                            setattr(game, str(attr_name), None)
                        elif path:
                            self.log_message(f"{path} does not exist")
                        elif attr_path_value:
                            self.log_message(f"{attr_path_value} does not exist")
                    except PermissionError as e:
                        self.log_message(f"Unable to delete files.': {e}")
                        return
            except Exception as e:
                self.log_message(f"Unable to delete '{str(game.title)} bin and obj': {e}")
                return


            self.drawer_update_labels(game)
            self.load_games(self.games)

    class ClickOverlay(QWidget):
        def __init__(self, launcher):
            super().__init__(launcher)
            self.launcher = launcher

        def mousePressEvent(self, event):
            self.launcher.hide_settings_drawer()

    def create_settings_drawer(self):

        self.overlay = self.ClickOverlay(self)
        self.overlay.setStyleSheet("background-color: rgba(0,0,0,120);")
        self.overlay.hide()

        self.settings_drawer = QFrame(self)
        self.settings_drawer.setObjectName("settingsDrawer")
        self.settings_drawer.setFixedWidth(950)

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

        self.drawer_create_labels(form)

        drawer_layout.addWidget(info_group)

        action_group = QGroupBox("Actions")
        action_group.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Maximum
        )
        actions = QHBoxLayout(action_group)
        actions.setContentsMargins(8, 8, 8, 8)
        # self.run_btn = QPushButton("Launch Game")
        self.validate1_btn = QPushButton("Convert (xnb-cli)")
        self.validate1_btn.clicked.connect(lambda: self.convert_content(tool_id=2))

        self.validate2_btn = QPushButton("Convert (xna-convert)")
        self.validate2_btn.clicked.connect(lambda: self.convert_content(tool_id=1))

        self.validate3_btn = QPushButton("Convert (xnb-extractor)")
        self.validate3_btn.clicked.connect(lambda: self.convert_content(tool_id=3))

        # self.open_folder_btn = QPushButton("Open Folder")
        # self.open_folder_btn.clicked.connect(self.open_selected_folder)
        self.delete_extracted = QPushButton("Delete Extracted")
        self.delete_extracted.clicked.connect(partial(self.delete_game_files, "extracted"))
        self.delete_decompiled = QPushButton("Delete Decompiled")
        self.delete_decompiled.clicked.connect(partial(self.delete_game_files, "decompiled"))
        self.delete_decompiled_bin = QPushButton("Delete Decompiled Bin and Obj Folders")
        self.delete_decompiled_bin.clicked.connect(partial(self.delete_game_files, "bin-obj"))
        # actions.addWidget(self.run_btn)
        actions.addWidget(self.validate1_btn)
        actions.addWidget(self.validate2_btn)
        actions.addWidget(self.validate3_btn)
        actions.addWidget(self.delete_extracted)
        actions.addWidget(self.delete_decompiled)
        actions.addWidget(self.delete_decompiled_bin)
        actions.addStretch()
        options_group = QGroupBox("Options")
        options_group.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Maximum
        )

        self.input_folder = QLabel("Input Folder")
        self.output_folder = QLabel("Output Folder")

        options = QFormLayout(options_group)
        options.setContentsMargins(8, 8, 8, 8)
        options.addRow("Input Folder", self.input_folder)
        options.addRow("Output Folder", self.output_folder)

        self.options = {x: QCheckBox(x) for x in (
            "loader", "parser", "extract", "compress",
            "convert-to-windows", "overwrite", "playaudio"
        )}

        checkboxes = QHBoxLayout()
        for option in self.options.values():
            checkboxes.addWidget(option)

        options.addRow("Options", checkboxes)

        drawer_layout.addWidget(action_group)
        drawer_layout.addWidget(options_group)
        drawer_layout.addStretch()
        self.settings_drawer.hide()

    def drawer_create_labels(self, form: QFormLayout):
        self.title_lbl = QLabel("-")
        self.titleid_lbl = QLabel("-")
        self.dll_files_lbl = QLabel("-")
        self.exe_lbl = QLabel("-")
        self.xml_lbl = QLabel("-")
        self.extracted_lbl = QLabel("-")
        self.decompiled_lbl = QLabel("-")
        self.archived_lbl = QLabel("-")
        self.status_lbl = QLabel("-")
        self.title_root_lbl = QLabel("-")

        form.addRow("Title", self.title_lbl)
        form.addRow("Title ID", self.titleid_lbl)
        form.addRow("DLL Files", self.dll_files_lbl)
        form.addRow("Executables", self.exe_lbl)
        form.addRow("GameInfo.xml", self.xml_lbl)
        form.addRow("Extracted", self.extracted_lbl)
        form.addRow("Decompiled", self.decompiled_lbl)
        form.addRow("Archived", self.archived_lbl)
        form.addRow("Status", self.status_lbl)
        form.addRow("Title Root", self.title_root_lbl)

    def build_ui(self):

        self.scan_btn = QPushButton("Scan Games")
        self.scan_btn.clicked.connect(self.rescan_games_responsive)
        self.extract_btn = QPushButton("Extract Game Package")
        self.extract_btn.clicked.connect(self.extract_game_package)
        self.build_btn = QPushButton("Decompile Game and Assemblies")
        self.build_btn.clicked.connect(self.decompile)
        # self.convert_project_btn = QPushButton("Convert Game Project Files")
        # self.convert_project_btn.clicked.connect(self.convert_game_project)
        self.open_folder_btn = QPushButton("Open Game Folder")
        self.open_folder_btn.clicked.connect(partial(self.open_selected_folder, "root"))
        self.open_folder_extracted_btn = QPushButton("Open Game Extracted Folder")
        self.open_folder_extracted_btn.clicked.connect(partial(self.open_selected_folder, "extracted"))
        self.compress_btn = QPushButton("Compress Selected Extracted Content")
        self.compress_btn.clicked.connect(partial(self.compress_decompress_extracted_content, True))
        self.decompress_btn = QPushButton("Decompress Selected Extracted Content")
        self.decompress_btn.clicked.connect(partial(self.compress_decompress_extracted_content, False))

        main_layout = QVBoxLayout(self)

        # -----------------------------
        # Top row - action buttons
        # -----------------------------
        button_row = QHBoxLayout()

        button_row.addWidget(self.scan_btn)
        button_row.addWidget(self.build_btn)
        button_row.addWidget(self.extract_btn)
        # button_row.addWidget(self.convert_project_btn)
        button_row.addWidget(self.open_folder_btn)
        button_row.addWidget(self.open_folder_extracted_btn)
        button_row.addWidget(self.compress_btn)
        button_row.addWidget(self.decompress_btn)

        main_layout.addLayout(button_row)

        # -----------------------------
        # Second row - options
        # -----------------------------
        options_row = QHBoxLayout()
        #
        # self.all_checkbox = QCheckBox("All or One")
        # self.all_checkbox.toggled.connect(self.all_or_one)
        self.config = load_config()
        self.overwrite_check = QCheckBox("Overwrite Extract")
        self.cache_check = QCheckBox("Override Cache")

        self.root_edit = QLineEdit()
        self.root_edit.setPlaceholderText("Indie Games Root folder...")
        self.root_edit.setFixedWidth(100)
        root_folder = self.config["indie_games_path"]
        self.root_edit.setText(root_folder)

        self.root_browse_btn = QPushButton("...")
        self.root_browse_btn.setFixedWidth(32)
        self.root_browse_btn.clicked.connect(partial(self.browse_root_folder, "indie_games_path"))

        # self.config = load_config_file()
        # self.config["indie-game-solution-location"] = str(r"C:\source\Indie-Games\Indie-Games.slnx")

        self.root_solution_edit = QLineEdit()
        self.root_solution_edit.setPlaceholderText("Indie Games Solution folder...")
        self.root_solution_edit.setMaximumWidth(500)
        root_folder = self.config["indie-game-solution-location"]
        self.root_solution_edit.setText(root_folder)

        self.root_solution_browse_btn = QPushButton("...")
        self.root_solution_browse_btn.setFixedWidth(32)
        self.root_solution_browse_btn.clicked.connect(partial(self.browse_root_folder, "indie-game-solution-location"))

        self.root_solution_arch = QLineEdit()
        self.root_solution_arch.setPlaceholderText("Indie Games Archive folder...")
        self.root_solution_arch.setMaximumWidth(500)
        root_folder_arch = Path(self.config["indie-game-solution-location"]).parent / "indie-game-archive"
        self.root_solution_arch.setText(str(root_folder_arch))

        self.open_ilspy_btn = QPushButton("Open ILSpy")
        self.open_ilspy_btn.clicked.connect(self.open_ilspy)

        # options_row.addWidget(self.all_checkbox)
        options_row.addWidget(self.overwrite_check)
        options_row.addWidget(self.cache_check)
        options_row.addWidget(self.root_edit, 1)
        options_row.addWidget(self.root_browse_btn)
        options_row.addWidget(self.root_solution_edit, 1)
        options_row.addWidget(self.root_solution_browse_btn)
        options_row.addWidget(self.root_solution_arch, 1)
        options_row.addWidget(self.open_ilspy_btn)

        options_row.addStretch()
        # self.all_checkbox.setSizePolicy(
        #     QSizePolicy.Policy.Fixed,
        #     QSizePolicy.Policy.Fixed,
        # )

        self.overwrite_check.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )

        self.cache_check.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )

        self.root_edit.setFixedWidth(400)
        self.root_browse_btn.setFixedWidth(32)

        main_layout.addLayout(options_row)

        #
        # Progress Bar
        #

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)

        main_layout.addWidget(self.progress_bar)
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
        self.game_table = QTableView()
        self.model = IndieGameTableModel()
        self.model.log.connect(self.log_message)
        self.game_table.setModel(self.model)
        self.game_table.setSortingEnabled(True)
        header = self.game_table.horizontalHeader()

        # Icon column
        header.setSectionResizeMode(
            0,
            QHeaderView.ResizeMode.Fixed,
        )
        header.resizeSection(0, 42)

        # Other columns
        for column in range(1, self.model.columnCount()):
            header.setSectionResizeMode(
                column,
                QHeaderView.ResizeMode.ResizeToContents,
            )

        self.game_table.setIconSize(QSize(32, 32))
        self.game_table.verticalHeader().setDefaultSectionSize(42)

        self.game_table.setItemDelegateForColumn(
            0,
            IconButtonDelegate(self.game_table),
        )

        self.game_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )

        self.game_table.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.game_table.setFocusPolicy(
            Qt.FocusPolicy.StrongFocus
        )
        self.game_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )

        self.game_table.selectionModel().selectionChanged.connect(
            self.game_selected
        )

        left_splitter.addWidget(self.game_table)

        #
        # Log Window
        #

        log_group = QGroupBox("Log")
        log_layout = QVBoxLayout(log_group)

        self.log_window = QPlainTextEdit()
        self.log_window.setReadOnly(True)
        self.log_window.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.log_window.setFont(QFont("Consolas", 9))

        log_layout.addWidget(self.log_window)

        left_splitter.addWidget(log_group)

        # Table gets ~80%, log gets ~20%
        left_splitter.setStretchFactor(0, 5)
        left_splitter.setStretchFactor(1, 2)
        # left_splitter.setStretchFactor(2, 2)
        left_layout.addWidget(left_splitter)

        splitter.addWidget(left)

        splitter.setStretchFactor(0, 1)

        main_layout.addWidget(splitter)

    def open_ilspy(self):
        ensure_tool_extracted("ilspy", log_callback=self.log_message, )
        self.ilspy_process = QProcess(self)
        self.ilspy_process.setProgram(str(ILSPY_GUI))
        self.ilspy_process.finished.connect(lambda: cleanup_tool("ilspy", self.log_message))
        self.ilspy_process.start()

    def _ilspy_finished(self):
        output = StringIO()

        with redirect_stdout(output):
            cleanup_tool("ilspy", None)

        for line in output.getvalue().splitlines():
            if line.strip():
                self.log_message(line)

    def browse_root_folder(self, type_of_folder=None):
        if type_of_folder == "indie_games_path":
            folder = QFileDialog.getExistingDirectory(
                self,
                "Select Indie Games Root Folder",
                self.root_edit.text(),
            )

            if folder:
                self.root_edit.setText(folder)
                self.config["indie_games_path"] = folder
                save_config(self.config)

        if type_of_folder == "indie-game-solution-location":
            folder, file = QFileDialog.getOpenFileName(
                self,
                "Select Indie Games Solution Folder",
                self.root_solution_edit.text(),
            )

            if folder:
                self.root_solution_edit.setText(folder)
                self.config["indie-game-solution-location"] = folder
                save_config(self.config)

    # def add_demo_game(self, title, status, extracted, exe):
    #
    #     row = self.game_table.rowCount()
    #
    #     self.game_table.insertRow(row)
    #
    #     self.game_table.setItem(row, 0, QTableWidgetItem(title))
    #     self.game_table.setItem(row, 1, QTableWidgetItem(status))
    #     self.game_table.setItem(row, 2, QTableWidgetItem(extracted))
    #     self.game_table.setItem(row, 3, QTableWidgetItem(exe))

    # def log_message(self, message, color=None):
    #     message = escape(str(message))
    #
    #     if color:
    #         message = f'<span style="color: {color};">{message}</span>'
    #
    #     self.log_window.appendHtml(message)

    def log_message(self, message, color=None, clear_console=False):
        logger_current = setup_logger()
        message = escape(str(message))
        if clear_console: self.log_window.clear()
        if color is None:
            color = RAINBOW_COLORS[self._rainbow_index]
            self._rainbow_index = (self._rainbow_index + 1) % len(RAINBOW_COLORS)
        if color == "debug":
            color = "green"
            logger_current.debug(f"{message}")
        logger_current.info(f"{message}")
        self.log_window.appendHtml(f'<span style="color: {color};">{message}</span>')


if __name__ == "__main__":
    logger = setup_logger()

    app = QApplication(sys.argv)
    xbdlg = XBLIGDialog()
    xbdlg.exec()

    # cleanup_nested_categories(r"C:\PycharmProjects\xenia-game-manager\src\downloads")
    #
    # move_folders_to_type(get_app_dir() / "downloads")
    #
    # exe = Path(get_app_dir() / "downloads" / "XBLIG" / "Alien Jelly (World) (XBLIG)/584E07D2/00000002/62F2648203AAB1C526B538091DF3BBE8CFC6E7E758_extracted/584E07D1/Game.exe")
    # if exe.exists(): read_bytes(exe)
