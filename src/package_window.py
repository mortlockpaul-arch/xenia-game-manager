import io
import logging
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

from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QRect, QThread, Signal, QObject, QModelIndex, \
    Slot, QSize, QProcess, QEvent
from PySide6.QtGui import QFont, QMouseEvent
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QWidget,
    QPushButton,
    QLabel,
    QTableWidgetItem,
    QFormLayout,
    QGroupBox,
    QHeaderView, QApplication, QSizePolicy, QFrame, QGraphicsDropShadowEffect, QCheckBox, QButtonGroup,
    QRadioButton, QProgressBar, QPlainTextEdit, QLineEdit, QAbstractItemView, QTableView, QFileDialog,
    QStyledItemDelegate,
)
from db import ConversionResult, Database, XBLIGGame, Game, GameSource

from config import get_app_dir, load_config_file, save_config
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
ILSPY_GUI = DECOMPILER / "ILSpy" / "publish" / "ILSpy.exe"
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

def copy_extracted_folder_content_and_references(source_content_root_folder, dest_content_folder, dll_files,
                                                 log_callback=None, ):
    source_content_root_folder = Path(source_content_root_folder)
    dest_content_folder = Path(dest_content_folder)

    log = log_callback or print

    if not source_content_root_folder.exists():
        archives = sorted(source_content_root_folder.parent.glob("Content*.7z"))

        if archives:
            log(f"Content folder missing, extracting {len(archives)} archive(s)...")
            for archive in archives:
                decompress_content(archive, source_content_root_folder.parent, log_callback=log)
        else:
            raise FileNotFoundError(
                f"Content folder or archive not found: {source_content_root_folder}"
            )

    # if dest_content_folder.exists() and dest_content_folder.is_dir():
    #     shutil.rmtree(dest_content_folder, ignore_errors=True)
    shutil.copytree(source_content_root_folder, dest_content_folder, dirs_exist_ok=True)

    for dll in dll_files:
        try:
            shutil.copy2(dll, dest_content_folder.parent / dll.name)
        except Exception as e:
            log(f"Failed to copy DLL {dll}: {type(e).__name__}: {e}")


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

    if show_command: log_callback(f"7-zip command: {arguments}")
    subprocess.run(arguments, check=True)
    log_callback(f"Decompression Completed")
    if delete_archive: archive.unlink()
    return output_dir


def compress_folders(root: Path, source_dirs, archive: Path, delete_original: bool = False, log_callback=None) -> Path:
    source_dirs = [source_dirs] if isinstance(source_dirs, Path) else [Path(p) for p in source_dirs]

    if archive.exists():
        archive.unlink()

    if log_callback:
        log_callback("Compressing: " + ", ".join(map(str, source_dirs)))

    relative_folders = [folder.relative_to(root) for folder in source_dirs]
    command = [str(get_7zip()), "a", "-t7z", "-mx=9", "-m0=lzma2", "-mmt=on", "-ms=on"]
    if delete_original:
        command.append("-sdel")
    command += [str(archive), *map(str, relative_folders)]

    result = subprocess.run(command, cwd=root, check=True, capture_output=True, text=True)

    if log_callback:
        log_callback(result.stdout)
        log_callback(result.stderr)

    if delete_original:
        for source_dir in source_dirs:
            if source_dir.exists():
                shutil.rmtree(source_dir)

    return archive


def ensure_tool_extracted(name: str, log=None):
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
    if log:
        for line in result.stdout.splitlines():
            if line.strip():
                log(line)




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


def get_cs_project_folders(
        games: list[XBLIGGame],
        log_callback: Callable[[str], None] | None = None,
) -> list[Path]:
    projects = []

    for game in games:
        if game.decompiled is None:
            continue

        assert game.folder_title is not None
        new_path = game.decompiled / f"{game.folder_title}.csproj"

        for project in game.decompiled.rglob("*.csproj"):
            if project == new_path:
                projects.append(project)
                continue

            if new_path.exists():
                if log_callback:
                    log_callback(
                        f"  Project already exists: {new_path.name}; "
                        f"removing duplicate {project.name}"
                    )
                project.unlink()
            else:
                try:
                    project.rename(new_path)
                    if log_callback:
                        log_callback(
                            f"  Renamed {project.name} -> {new_path.name}"
                        )
                except PermissionError:
                    log_callback(f"Could not Rename {project.name}. Maybe its open in Visual Studio.")

            if new_path not in projects:
                projects.append(new_path)

    return projects


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


class ConvertXnaProjects(QObject):
    log_signal = Signal(str, str)
    progress_signal = Signal(int, int)
    finished_signal = Signal(ConversionResult)
    total_files_signal = Signal(int)

    def __init__(self, project_path, games, options, /):
        super().__init__()

        self._rainbow_index = 1
        self.config = load_config_file()
        self.options: dict[str, QCheckBox] = options
        self.project_path = Path(project_path)
        self.games = games

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

    def log_message(self, message, color=None):
        if color is None:
            color = self.RAINBOW_COLORS[self._rainbow_index]
            self._rainbow_index = (self._rainbow_index + 1) % len(self.RAINBOW_COLORS)
        self.log_signal.emit(message, color)

    from pathlib import Path

    def find_packages(self, root: str | Path):
        root = Path(root)

        games: list[XBLIGGame] = []
        packages: list[Path] = []

        stfs_magic = {b"CON ", b"LIVE", b"PIRS"}

        # ================================================================
        # Helpers
        # ================================================================

        def is_stfs(path: Path) -> bool:
            try:
                with path.open("rb") as f:
                    return f.read(4) in stfs_magic
            except OSError:
                return False

        def scan_files(folder: Path):
            """
            Recursively yield files as Path objects.
            """
            try:
                with os.scandir(folder) as entries:
                    for entry in entries:
                        try:
                            path = Path(entry.path)

                            if entry.is_file(follow_symlinks=False):
                                yield path

                            elif entry.is_dir(follow_symlinks=False):
                                yield from scan_files(path)

                        except OSError:
                            continue

            except OSError:
                return

        def parse_xml(xml_file: Path) -> dict:
            if not xml_file.exists():
                return {}

            try:
                title_info = (
                    ET.parse(xml_file)
                    .getroot()
                    .find(".//TitleInfo")
                )

                if title_info is None:
                    return {}

                return {
                    "title": title_info.attrib.get("Name"),
                    "virtual_title_id": title_info.attrib.get(
                        "VirtualTitleID"
                    ),
                    "xml_title_id": title_info.attrib.get(
                        "TitleID"
                    ),
                    "image_path": title_info.attrib.get(
                        "ImagePath"
                    ),
                }

            except Exception as e:
                self.log_message(
                    f"XML error: {xml_file} ({e})"
                )
                return {}

        # ================================================================
        # PASS 1
        #
        # Traverse the ENTIRE supplied root.
        #
        # At the same time:
        #   - count files
        #   - count folders
        #   - locate 584E07D2
        #
        # No files are opened during this pass.
        # ================================================================

        self.log_message(
            f"Scanning folders: {root}"
        )
        total_files = 0
        total_folders = 0

        indie_folders: list[Path] = []

        folders_to_scan = [root]

        while folders_to_scan:
            folder = folders_to_scan.pop()

            try:
                with os.scandir(folder) as entries:
                    for entry in entries:
                        try:
                            if entry.is_file(
                                    follow_symlinks=False
                            ):
                                total_files += 1

                                # Log every 1,000 files.
                                if total_files % 1000 == 0:
                                    self.log_message(
                                        f"Scanned "
                                        f"{total_files:,} files "
                                        f"across "
                                        f"{total_folders:,} folders..."
                                    )

                                continue

                            if not entry.is_dir(
                                    follow_symlinks=False
                            ):
                                continue

                            total_folders += 1

                            path = Path(entry.path)

                            # ------------------------------------------------
                            # Found an XBLIG content folder
                            # ------------------------------------------------

                            if entry.name.upper() == "584E07D2":
                                indie_folders.append(path)

                                self.log_message(
                                    f"Found 584E07D2: {path}"
                                )

                                # Don't search inside this folder for
                                # another 584E07D2.
                                continue

                            folders_to_scan.append(path)

                        except OSError:
                            continue

            except OSError:
                continue

        # ================================================================
        # Scan summary
        # ================================================================

        self.log_message(
            "Folder scan complete."
        )

        self.log_message(
            f"Folders scanned: {total_folders:,}"
        )

        self.log_message(
            f"Files found: {total_files:,}"
        )

        self.log_message(
            f"584E07D2 folders found: "
            f"{len(indie_folders):,}"
        )

        # Tell the progress bar the actual number of files.
        self.total_files_signal.emit(total_files)

        # ================================================================
        # PASS 2
        #
        # Look only inside discovered 584E07D2 folders.
        # ================================================================

        self.log_message(
            "Scanning XBLIG package folders..."
        )

        files_scanned = 0
        last_progress = -1

        for indie_index, indie_folder in enumerate(indie_folders, start=1,):
            self.log_message(
                f"[XBLIG folder "
                f"{indie_index}/{len(indie_folders)}]"
            )

            self.log_message(
                f"  {indie_folder}"
            )

            package_folder = indie_folder / "00000002"

            if not package_folder.is_dir():
                self.log_message(
                    "  └─ 00000002 not found"
                )
                continue

            self.log_message(
                f"  └─ Scanning: {package_folder}"
            )

            for path in scan_files(package_folder):
                files_scanned += 1

                # First 25% of progress is the package scan.
                progress = int(
                    files_scanned * 25
                    / max(total_files, 1)
                )

                if progress != last_progress:
                    self.progress_signal.emit(total_files, total_files)
                    last_progress = progress

                if files_scanned % 1000 == 0:
                    self.log_message(
                        f"Scanned "
                        f"{files_scanned:,} / "
                        f"{total_files:,} files..."
                    )

                if is_stfs(path):
                    packages.append(path)

                    self.log_message(
                        f"  STFS package found: "
                        f"{path}"
                    )

        # ================================================================
        # Package summary
        # ================================================================

        self.log_message(
            f"Found {len(packages):,} STFS package(s)."
        )

        if not packages:
            self.progress_signal.emit(total_files, total_files)

            self.log_message(
                "==================="
            )
            self.log_message(
                "Scanner found 0 XBLIG game(s)."
            )

            return games

        # ================================================================
        # PASS 3
        #
        # Process the discovered packages.
        # ================================================================

        total_packages = len(packages)

        self.log_message(
            f"Processing {total_packages:,} package(s)..."
        )

        for index, package in enumerate(
                packages,
                start=1,
        ):
            # Package processing = remaining 75%.
            progress = 25 + int(
                index * 75
                / max(total_packages, 1)
            )

            self.progress_signal.emit(total_files, total_files)

            self.log_message(
                f"[Package "
                f"{index}/{total_packages}]"
            )

            self.log_message(
                f"  {package}"
            )

            # ------------------------------------------------------------
            # Game folder
            # ------------------------------------------------------------

            folder_title = (
                package.parents[2].name
                if len(package.parents) >= 3
                else package.parent.name
            )

            # ------------------------------------------------------------
            # Paths
            # ------------------------------------------------------------

            indie_games_path = Path(
                self.config["indie_games_path"]
            )

            decompiled = (
                    indie_games_path
                    / "decompiled"
                    / folder_title
            )

            extracted = (
                    indie_games_path
                    / "extracted"
                    / folder_title
            )

            game_info = extracted / "GameInfo.xml"


            xml_data = parse_xml(game_info)

            title = (
                    xml_data.get("title")
                    or folder_title
                    or package.stem
            )

            title_id = package.stem.upper()
            title_id = xml_data.get("xml_title_id") or title_id

            decompiled_path_value = (
                    package.parent / "decompiled"
            )

            extracted_path_value = (
                    package.parent / "extracted"
            )

            # ------------------------------------------------------------
            # Runtime profile
            # ------------------------------------------------------------

            profile_string = (
                    decompiled
                    / "Microsoft.Xna.Framework.RuntimeProfile"
            )

            try:
                content_format = (
                    profile_string.read_text().strip()
                    if profile_string.exists()
                    else ""
                )
            except OSError:
                content_format = ""

            # ------------------------------------------------------------
            # EXEs and DLLs
            # ------------------------------------------------------------

            exe_files: list[Path] = []
            dll_files: list[Path] = []

            if extracted.is_dir():
                self.log_message(
                    f"  Scanning extracted: "
                    f"{extracted}"
                )

                extracted_files = 0

                for path in scan_files(extracted):
                    extracted_files += 1

                    suffix = path.suffix.lower()

                    if suffix == ".exe":
                        exe_files.append(path)

                    elif suffix == ".dll":
                        dll_files.append(path)

                self.log_message(
                    f"  Scanned "
                    f"{extracted_files:,} extracted files"
                )

            self.log_message(
                f"  Executables: "
                f"{len(exe_files):,}"
            )

            self.log_message(
                f"  DLLs: "
                f"{len(dll_files):,}"
            )

            # ------------------------------------------------------------
            # Create game
            # ------------------------------------------------------------

            games.append(
                XBLIGGame(
                    title=title,
                    folder_title=folder_title,
                    title_id=title_id,
                    game_id=title_id,
                    virtual_title_id=xml_data.get( "virtual_title_id" ),
                    xml_title_id=xml_data.get( "xml_title_id" ),
                    content_type=content_format,
                    content_name="Xbox Live Indie Game",
                    content_format=content_format,
                    package=package,
                    extracted=(
                        extracted
                        if extracted.exists()
                        else (
                            extracted_path_value
                            if extracted_path_value.exists()
                            else None
                        )
                    ),

                    game_root=(
                        extracted
                        if extracted.exists()
                        else package.parent
                    ),

                    executables=exe_files,
                    dll_files=dll_files,

                    xml=(
                        game_info
                        if game_info.exists()
                        else None
                    ),

                    decompiled=(
                        decompiled
                        if decompiled.exists()
                        else (
                            decompiled_path_value
                            if decompiled_path_value.exists()
                            else None
                        )
                    ),
                )
            )

            self.log_message(
                f"  Processed: {title}"
            )

        # ================================================================
        # Finished
        # ================================================================

        self.progress_signal.emit(files_scanned, total_files)

        self.log_message("")
        self.log_message(
            "==================="
        )

        self.log_message(
            f"Scanner found "
            f"{len(games):,} XBLIG game(s)."
        )

        return games

    def convert_xnb_folder_tools(self, game: XBLIGGame, tool_id: int = 1):

        if game.extracted is None:
            self.log_message(f"Game not extracted: {game}")
            return None

        content_dir = game.extracted / "584E07D1" / "Content"
        output_dir = content_dir.parent / "Content_Output"

        if not content_dir.exists():
            self.log_message(f"Content folder not found: {content_dir}")
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
            self.log_message(f"Unknown tool id: {tool_id}")
            return None

        self.log_message(f"Running {tool_name}...")

        try:
            stdout_lines = []
            stderr_lines = []

            self.log_message("Full command:")
            self.log_message(" ".join(cmd))

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
                    self.log_message(line)

                for line in process.stderr:
                    line = line.rstrip()
                    stderr_lines.append(line)
                    self.log_message(f"ERR: {line}")

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

            self.log_message(
                f"{tool_name}: {'SUCCESS' if success else 'FAILED'}"
            )

            self.log_message(
                f"Generated files: {len(output_files)}"
            )

            if not success:
                failed_folders.append(content_dir)

            self.finished_signal.emit(result)

        except Exception as e:

            failed_folders.append(content_dir)

            self.log_message(
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

        self.log_message("===================")
        self.log_message("Conversion complete")
        self.log_message(
            f"Failed folders: {len(failed_folders)}"
        )

        for folder in failed_folders:
            self.log_message(str(folder))

        return result

    from pathlib import Path

    def clean_csproj(self, project_path: Path, game_dll_files=None) -> None:
        project_path = Path(project_path)

        self.log_message(f"Updating project: {project_path.name}")
        self.log_message(f"  Project path: {project_path}")

        tree = ET.parse(project_path)
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

        assembly_name = next(
            (
                assembly.text.strip()
                for group in root.findall(tag("PropertyGroup"))
                for assembly in [group.find(tag("AssemblyName"))]
                if assembly is not None and assembly.text
            ),
            None,
        )

        if assembly_name:
            self.log_message(f"  Preserving AssemblyName: {assembly_name}")
        else:
            self.log_message("  No AssemblyName found; using project default.")

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

        self.log_message(
            f"  Removed {removed_properties} PropertyGroup(s) "
            f"and {removed_items} ItemGroup(s)."
        )

        # ---------------------------------------------------------
        # Properties
        # ---------------------------------------------------------

        propgroup = ET.SubElement(root, tag("PropertyGroup"))

        if assembly_name:
            ET.SubElement(propgroup, tag("AssemblyName")).text = assembly_name

        properties = {
            "GenerateAssemblyInfo": "false",
            "TargetFramework": "net10.0",
            "ImplicitUsings": "enable",
            "Nullable": "enable",
            "Platforms": "AnyCPU",
            "OutputType": "WinExe",
            "LangVersion": "14.0",
            "AllowUnsafeBlocks": "True",
            "CheckForOverflowUnderflow": "False",
        }

        for name, value in properties.items():
            ET.SubElement(propgroup, tag(name)).text = value
            self.log_message(f"    {name} = {value}")

        # ---------------------------------------------------------
        # Contents.csproj
        # ---------------------------------------------------------

        content_project = Path(r"..\..\Content-References\Contents.csproj")

        self.log_message(
            f"  Adding project reference: {content_project}"
        )

        itemgroup = ET.SubElement(root, tag("ItemGroup"))

        reference = ET.SubElement(
            itemgroup,
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
            self.log_message(f"  Adding {len(game_dll_files)} game DLL reference(s)...")

            dll_group = ET.SubElement(root, tag("ItemGroup"))

            for dll in map(Path, game_dll_files):
                reference = ET.SubElement(
                    dll_group,
                    tag("Reference"),
                    {"Include": dll.stem},
                )

                ET.SubElement(reference, tag("HintPath")).text = dll.name
                ET.SubElement(reference, tag("Private")).text = "True"

                self.log_message(f"    Added DLL: {dll.name}")
        else:
            self.log_message("  No game DLL references supplied.")

        # ---------------------------------------------------------
        # Content files
        # ---------------------------------------------------------

        self.log_message(
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
        tree.write(project_path, encoding="utf-8", xml_declaration=True)

        self.log_message(
            f"  Project updated successfully: {project_path.name}"
        )

    from pathlib import Path
    def copy_project_files(
            self,
            source_dir: Path,
            destination_dir: Path,
    ) -> bool:
        self.log_message(f"  Copying project files to: {destination_dir}")

        try:
            destination_dir.mkdir(parents=True, exist_ok=True)

            for source in source_dir.iterdir():
                if source.is_file():
                    shutil.copy2(source, destination_dir / source.name)
                    self.log_message(f"    Copied: {source.name}")

        except OSError as exc:
            self.log_message(f"  ERROR copying project files: {exc}")
            return False

        self.log_message("  Project files copied successfully.")
        return True

    LOG_COLORS = {
        "normal": "#D4D4D4",  # Light grey
        "info": "#61AFEF",  # Blue
        "success": "#98C379",  # Green
        "warning": "#E5C07B",  # Yellow/orange
        "error": "#E06C75",  # Red
        "debug": "#C678DD",  # Purple
    }

    def add_project_to_solution(self, solution_path: Path, project_path: Path,) -> bool:
        solution_path = Path(solution_path).resolve()
        project_path = Path(project_path).resolve()

        self.log_message(f"Adding project to solution: {project_path.name}", self.LOG_COLORS["debug"])

        if not solution_path.exists():
            self.log_message(f"  Solution not found: {solution_path}")
            return False

        if not project_path.exists():
            self.log_message(f"  Project not found: {project_path}")
            return False

        # ---------------------------------------------------------
        # Destination
        # ---------------------------------------------------------

        archive_dir = solution_path.parent / "indie-game-archive"
        archive_dir.mkdir(parents=True, exist_ok=True)

        project_dir = project_path.parent
        destination_dir = archive_dir / project_dir.name
        destination_project = destination_dir / project_path.name

        self.log_message(f"  Source:      {project_dir}")
        self.log_message(f"  Destination: {destination_dir}")

        # ---------------------------------------------------------
        # Move / synchronise project
        # ---------------------------------------------------------

        if project_dir.resolve() != destination_dir.resolve():

            if destination_dir.exists():
                self.log_message("  Destination already exists.")

                projects = list(destination_dir.rglob("*.csproj"))

                if destination_project.exists():
                    if not self.copy_project_files(project_dir, destination_dir):
                        return False

                    project_path = destination_project
                    self.log_message(
                        f"  Updated existing project: {project_path.name}"
                    )

                elif len(projects) == 1:
                    try:
                        projects[0].rename(destination_project)
                        if not self.copy_project_files(project_dir, destination_dir):
                            return False
                        project_path = destination_project
                        self.log_message(
                            f"  Renamed {projects[0].name} -> "
                            f"{destination_project.name}"
                        )
                    except OSError as exc:
                        self.log_message(f"  ERROR renaming project: {exc}")
                        return False

                elif not projects:
                    self.log_message("  ERROR: No .csproj found in destination.")
                    return False

                else:
                    self.log_message(
                        f"  ERROR: Found {len(projects)} .csproj files "
                        "in destination."
                    )
                    return False

            else:
                self.log_message(f"  Moving project to: {destination_dir}")

                try:
                    shutil.move(str(project_dir), str(destination_dir))
                except OSError as exc:
                    self.log_message(f"  ERROR moving project: {exc}")
                    return False

                project_path = destination_project
                self.log_message("  Project moved successfully.")

        else:
            self.log_message("  Project is already in the destination.")

        # ---------------------------------------------------------
        # Solution project path
        # ---------------------------------------------------------

        try:
            project_path_value = os.path.relpath(
                project_path,
                solution_path.parent,
            ).replace("\\", "/")
        except ValueError:
            project_path_value = project_path.as_posix()
            self.log_message("  Project is on a different drive.")

        self.log_message(f"  Solution path: {project_path_value}")

        # ---------------------------------------------------------
        # Parse solution
        # ---------------------------------------------------------

        try:
            tree = ET.parse(solution_path)
        except ET.ParseError as exc:
            self.log_message(f"  ERROR reading solution: {exc}")
            return False

        root = tree.getroot()
        project_name = project_path.stem
        destination_dir = destination_dir.resolve()

        # ---------------------------------------------------------
        # Remove existing entries
        # ---------------------------------------------------------

        removed = 0

        for parent in root.iter():
            for project in list(parent):
                if project.tag != "Project":
                    continue

                existing_path = project.get("Path")
                if not existing_path:
                    continue

                existing = Path(existing_path)

                if not existing.is_absolute():
                    existing = solution_path.parent / existing

                try:
                    existing = existing.resolve()
                except OSError:
                    continue

                same_name = existing.stem.lower() == project_name.lower()
                same_location = (
                        existing == project_path
                        or destination_dir in existing.parents
                )

                if same_name or same_location:
                    self.log_message(
                        f"  Removing duplicate solution entry: {existing_path}"
                    )
                    parent.remove(project)
                    removed += 1

        if removed:
            self.log_message(f"  Removed {removed} duplicate solution entry(s).")

        # ---------------------------------------------------------
        # Find / create archive folder
        # ---------------------------------------------------------

        folder = next(
            (
                element for element in root.findall("Folder")
                if element.get("Name") == "/indie-game-archive/"
            ),
            None,
        )

        if folder is None:
            self.log_message("  Creating /indie-game-archive/ solution folder.")
            folder = ET.SubElement(
                root,
                "Folder",
                {"Name": "/indie-game-archive/"},
            )

        # ---------------------------------------------------------
        # Add project
        # ---------------------------------------------------------

        ET.SubElement(
            folder,
            "Project",
            {"Path": project_path_value},
        )

        self.log_message(
            f"  Added {project_path.name} to /indie-game-archive/"
        )

        # ---------------------------------------------------------
        # Save
        # ---------------------------------------------------------

        ET.indent(tree, space="  ")

        try:
            tree.write(
                solution_path,
                encoding="utf-8",
                xml_declaration=False,
            )
        except OSError as exc:
            self.log_message(f"  ERROR saving solution: {exc}")
            return False

        self.log_message("  Solution updated successfully.")
        return True

    def convert_project_folder(self, path_to_csproj_file: Path, add_to_solution=True, game_dll_files=None):
        try:
            self.clean_csproj(path_to_csproj_file, game_dll_files)

            if add_to_solution:
                solution_path = Path(r"C:\source\Indie-Games\Indie-Games.slnx")
                self.add_project_to_solution(
                    solution_path,
                    path_to_csproj_file,
                )

            # add_xna_compat(folder.parent)
            # self.remove_xna_usings(folder.parent)

        except Exception as e:
            self.log_message(f"FAILED {path_to_csproj_file}: {e}")

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


def _decompress_games(games: list[XBLIGGame], log):
    for i, game in enumerate(games, 1):
        if game.extracted is None or not game.package:
            continue
        root = game.extracted / "584E07D1"
        archive = root / "Content.7z"

        try:
            log(f"[{i}/{len(games)}] Decompressing {game.title}: {archive} folder(s)")
            decompress_content(archive, root, log_callback=log, delete_archive=True)

        except Exception as e:
            log(f"Failed to decompress {game.title}: {type(e).__name__}: {e}")


def _compress_games(games: list[XBLIGGame], log):
    for i, game in enumerate(games, 1):
        if game.extracted is None or not game.package:
            continue

        root = game.extracted / "584E07D1"
        xnb_files = list(root.rglob("*.xnb"))
        xnb_folders = list({p.parent for p in xnb_files})

        if not xnb_folders:
            log(f"No XNB folders found for {game.title}: {root}")
            continue

        content_folders = [
            p for p in xnb_folders
            if not any(parent in xnb_folders for parent in p.parents)
        ]

        archive = root / "Content.7z"

        try:
            log(
                f"[{i}/{len(games)}] Compressing {game.title}: "
                f"{len(content_folders)} folder(s)"
            )

            compress_folders(root, content_folders, archive, True, log_callback=log)

        except Exception as e:
            log(
                f"Failed to compress {game.title}: "
                f"{type(e).__name__}: {e}"
            )


class CompressWorker(QObject):
    log = Signal(str)
    finished = Signal()

    def __init__(self, function: Callable[..., None], *args, **kwargs, ):
        super().__init__()
        self.function = function
        self.args = args
        self.kwargs = kwargs

    @Slot()
    def run(self):
        with redirect_stdout(QtLogger(self.log.emit)):
            self.function(*self.args, **self.kwargs)
            self.finished.emit()


class ScanWorker(QObject):
    finished_signal = Signal(list)
    log_signal = Signal(str, str)
    progress_signal = Signal(int, int)
    total_files_signal = Signal(int)

    def __init__(self, root: Path, parent: XBLIGDialog, force: bool = False, ):
        super().__init__()
        converter = parent.method_name()
        self.total_files = 0
        self.root = root
        self.converter = converter
        self.force = force

    def _set_total_files(self, total: int):
        self.total_files = total
        self.total_files_signal.emit(total)
        # Forward converter signals
        # self.converter.log_signal.connect(self.log_signal)
        # self.converter.progress_signal.connect(self.progress_signal)

    @Slot()
    def run(self):

        try:
            games: list[XBLIGGame] = []
            # current_mtime = get_folder_mtime(self.root)
            cache = None if self.force else load_cache()
            if cache:
                self.log_message("Checking game cache...")
                games = cache["games"]
                self.log_message(f"Loaded {len(games)} games from cache.")
                self.total_files_signal.emit(100)
            else:
                self.log_message("Scanning folders...")
                if not self.root.exists():
                    self.log_message(f"Folder {self.root} does not exist.")
                    self.total_files_signal.emit(100)
                else:
                    games = self.converter.find_packages(self.root)
                    save_cache(games)
                    self.log_message("Cache updated.")
            self.finished_signal.emit(games)

        except Exception as e:
            self.log_message(f"Scanner error: {e}")
            self.finished_signal.emit([])

    def log_message(self, message: str, color: str = "#61AFEF"):
        self.log_signal.emit(message, color)

from PySide6.QtWidgets import QStyledItemDelegate
from PySide6.QtGui import QPainter
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

class XBLIGDialog(QDialog):

    def moby_games_lookup(self):
        config = load_config_file()

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

    def __init__(self, parent=None):
        super().__init__(parent)
        self.ilspy_process = None
        self._rainbow_index = 1
        self.conn = None
        self.scan_worker = None
        self.scan_thread = None
        self.config = load_config_file()
        self.columns = None
        self.game = None
        self.extracted = None
        self.overwrite_check = None
        self.compress_worker: CompressWorker | None = None
        self.worker = None
        self.compress_thread = None
        self.decompress_btn = None
        self.all_checkbox = None
        self.options = None
        self.drawer_open = False
        self._last_mtime = None
        self._cache = None
        self.compress_btn = None
        self.games: list[XBLIGGame] = []
        self.setWindowTitle("XBLIG Rebuilder")
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

            for key, value in game.items():
                label = key.replace("_", " ").title()
                print(f"{label:<15}: {value}")

            print()


    def get_selected_game(
            self,
    ) -> tuple[XBLIGGame, list[QModelIndex]] | None:

        indexes = self.game_table.selectionModel().selectedRows()

        if not indexes:
            return None

        game = self.model.get_game_from_index(indexes[0])

        return game, indexes

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

    def method_name(self) -> ConvertXnaProjects:
        converter = ConvertXnaProjects(get_app_dir(), self.games, self.options)
        converter.log_signal.connect(self.log_message)
        converter.progress_signal.connect(self.update_progress)
        converter.finished_signal.connect(self.tool_finished)
        converter.total_files_signal.connect(self.update_progress)
        return converter

    def update_progress(self, value: int):
        self.progress_bar.setValue(value)
        self.progress_bar.setFormat(
            f"Scanner {value}%"
        )

    def convert_game_project(self):
        if self.all_checkbox.isChecked():
            games = self.games
        else:
            if (result := self.get_selected_game()) is None:
                return
            game, _ = result
            games = [game]

        self.log_message(f"\nChecking {len(games)} Xbox Live Indie Games\n")
        converter = self.method_name()

        projects = get_cs_project_folders(games, self.log_message)

        print(f"Found {len(projects)} projects")

        for project in projects:
            try:
                converter.convert_project_folder(project, True)
            except Exception as e:
                print(
                    f"FAILED {project}: {e}"
                )

    def convert_content(self, tool_id=1):
        self.validate1_btn.setDisabled(True)
        self.validate2_btn.setDisabled(True)
        self.validate3_btn.setDisabled(True)
        if (result := self.get_selected_game()) is None:
            return
        game, indexes = result
        if game:
            ensure_tool_extracted("conversion", None)
            converter = self.method_name()

            self.progress_bar.setRange(0, 0)  # Busy animation
            run_in_background(converter.convert_xnb_folder_tools, game, tool_id)

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
            self.log_message_log(
                f"{result.tool}: SUCCESS - "
                f"{len(result.output_files)} files created."
            )
        else:
            self.log_message_log(
                f"{result.tool}: FAILED"
            )

            if result.error:
                self.log_message_log(result.error)

            if result.stderr:
                self.log_message_log(result.stderr)

    def decompile_project(self, game: XBLIGGame, dll_files: list[Path], parent=None, use_gui=False,
                          open_explorer=None) -> Path:

        if use_gui:
            ensure_tool_extracted("ilspy", None)
        else:
            ensure_tool_extracted("ilspycmd", None)

        ilspy_exe = ILSPY_GUI if use_gui else ILSPY_CMD

        assert game.folder_title is not None
        assert game.extracted is not None

        game_root_name = Path(game.folder_title)
        extracted_name = Path(game.extracted).name

        attrs = {
            "decompiled": (
                "decompiled",
                Path(self.config["indie_games_path"]) / "decompiled" / game_root_name
            ),
            "extracted": (
                "extracted",
                Path(self.config["indie_games_path"]) / "extracted" / extracted_name
            ),
        }

        attr_name, decompiled = attrs["decompiled"]
        attr_name, extracted = attrs["extracted"]

        output_dir = decompiled
        output_dir.mkdir(parents=True, exist_ok=True)

        self.log_message(f"Output Folder: {output_dir}")
        self.log_message(f"ILSpy: {ilspy_exe}")
        assert game.executables is not None
        for executable in game.executables:
            self.log_message(f"Generating Visual Studio project for {executable.name}...")

            if not use_gui:
                arguments = [
                    "-p",
                    "-o",
                    str(output_dir),
                    "-r",
                    str(executable.parent),
                    "--nested-directories",
                    str(executable),
                ]
            else:
                arguments = [
                    str(executable),
                ]

            process = QProcess(parent)
            process.setProgram(str(ilspy_exe))
            process.setArguments(arguments)
            if extracted: process.setWorkingDirectory(str(extracted))

            self.log_message(f"Command: {ilspy_exe} {' '.join(arguments)}")
            self.log_message(f"Working directory: {process.workingDirectory()}")

            if not use_gui:
                process.readyReadStandardOutput.connect(
                    lambda: self.log_message(
                        bytes(
                            process.readAllStandardOutput().data()
                        ).decode(
                            "utf-8",
                            errors="replace",
                        )
                    )
                )

                process.readyReadStandardError.connect(
                    lambda: self.log_message(
                        bytes(
                            process.readAllStandardError().data()
                        ).decode(
                            "utf-8",
                            errors="replace",
                        )
                    )
                )

            process.errorOccurred.connect(
                lambda error: self.log_message(
                    f"ILSpy process error: {error}"
                )
            )

            process.started.connect(
                lambda: self.log_message(
                    f"ILSpy started: {executable.name}"
                )
            )

            process.finished.connect(
                lambda exit_code, exit_status:
                self.on_decompile_finished(
                    open_explorer,
                    output_dir,
                    game,
                    exit_code,
                    exit_status,
                )
            )

            self.log_message("Starting ILSpy...")
            process.start()

        for dll in dll_files:
            if not use_gui:
                arguments = [
                    "-p",
                    "-o",
                    str(output_dir),
                    "--nested-directories",
                    str(dll),
                ]
            else:
                arguments = [
                    str(dll),
                ]

            process = QProcess(parent)
            process.setProgram(str(ilspy_exe))
            process.setArguments(arguments)
            if extracted: process.setWorkingDirectory(str(extracted))

            self.log_message(f"Command: {ilspy_exe} {' '.join(arguments)}")
            self.log_message(f"Working directory: {process.workingDirectory()}")

            if not use_gui:
                process.readyReadStandardOutput.connect(
                    lambda: self.log_message(
                        bytes(
                            process.readAllStandardOutput().data()
                        ).decode(
                            "utf-8",
                            errors="replace",
                        )
                    )
                )

                process.readyReadStandardError.connect(
                    lambda: self.log_message(
                        bytes(
                            process.readAllStandardError().data()
                        ).decode(
                            "utf-8",
                            errors="replace",
                        )
                    )
                )

            process.errorOccurred.connect(
                lambda error: self.log_message(
                    f"ILSpy process error: {error}"
                )
            )

            process.started.connect(
                lambda: self.log_message(
                    f"ILSpy started: {executable.name}"
                )
            )

            process.finished.connect(
                lambda exit_code, exit_status:
                self.on_decompile_finished(
                    open_explorer,
                    output_dir,
                    game,
                    exit_code,
                    exit_status,
                )
            )

            self.log_message("Starting ILSpy...")
            process.start()

        return output_dir

    def decompile_selected(self, game: XBLIGGame, open_explorer: bool = True, use_gui=False, ):
        executables = game.executables
        dlls = game.dll_files
        if not executables: raise ValueError("No Executables: Extract the game first.")

        try:
            project_dir = self.decompile_project(game, dlls, parent=self, use_gui=use_gui, open_explorer=open_explorer)
            if game.decompiled is None:
                game.decompiled = project_dir
        except Exception as e:
            self.log_message(
                f"ERROR decompiling {game.title}: "
                f"{type(e).__name__}: {e}"
            )
            self.log_message(traceback.format_exc())

    def on_decompile_finished(self, open_explorer, project_dir, game, exit_code, exit_status, ):
        self.log_message(f"ILSpy finished: exit code={exit_code}, status={exit_status}")

        if exit_code != 0:
            self.log_message(
                f"ILSpy failed while decompiling {game.title}"
            )
            return

        profile_string = (
                project_dir / "Microsoft.Xna.Framework.RuntimeProfile"
        )

        if profile_string.exists():
            game.content_format = profile_string.read_text().strip()
        else:
            game.content_format = ""

        game.decompiled = project_dir

        self.log_message(
            f"Decompiled project: {project_dir}"
        )

        if open_explorer:
            subprocess.Popen(["explorer", str(project_dir)])

    def update_scan_progress(self, current: int, total: int):
        value = int(current * 100 / total) if total else 0
        self.progress_bar.setValue(value)
        self.progress_bar.setFormat(f"Scanner {current:,}")

    def rescan_games_responsive(self, force=False):
        root = Path(self.config["indie_games_path"])

        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Scanner 0")
        self.scan_btn.setEnabled(False)

        if self.cache_check.isChecked():
            force = True

        thread = QThread(self)
        self.scan_thread = thread
        self.scan_worker = ScanWorker(root, self, force=force)
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

    def log_message_log(self, message):
        logging.info(f"{message}")
        self.log_message(message, "#2ecc71")

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

        self.update_labels(game)
        self.show_settings_drawer()

    def update_labels(self, game: XBLIGGame):
        relative_paths = False

        root = Path("D:/") / "downloads"

        self.title_lbl.setText(game.title)

        self.titleid_lbl.setText(
            game.title_id or "-"
        )

        self.dll_files_lbl.setText(
            "\n".join(dll.name for dll in game.dll_files) if game.dll_files else "-"
        )

        if game.executables:
            self.exe_lbl.setText(
                "\n".join(executable.name for executable in game.executables) if game.executables else "-")
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

        if game.decompiled:
            self.decompiled_lbl.setText(str(game.decompiled))
        else:
            self.decompiled_lbl.setText("-")

    def compress_decompress_extracted_content(self, mode: bool):
        selected = self.get_selected_game()
        games: list[XBLIGGame] = self.games if self.all_checkbox.isChecked() else []
        if selected is not None:
            games = [selected[0]]

        self.log_message(f"\nChecking {len(games)} Xbox Live Indie Games\n")
        if not games:
            return

        if mode:
            func = partial(_compress_games, games, self.log_message)
        else:
            func = partial(_decompress_games, games, self.log_message)
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

        self.game.extracted = self.extracted
        self.game.exe = next(self.extracted.rglob("*.exe"), None)

        self.log_message(f"Extracted {self.game.title} successfully")
        save_cache(self.games)
        self.load_games(self.games)

    def extract_game(self, game=None):
        if game is None:
            if (result := self.get_selected_game()) is None:
                return
            game, _ = result

        # if game.extracted is not None:
        #     self.log_message(f"{game.title} Already Extracted.")
        #     return

        if not game.package:
            self.log_message(f"{game.title} has no package.")
            return

        try:
            extracted = self.extract_package(game)

            if extracted is None:
                self.log_message(f"Failed to extract {game.title}")
                return
            #
            # game.extracted = extracted
            # game.exe = next(extracted.rglob("*.exe"), None)
            #
            # self.log_message(f"Extracted {game.title} successfully")
            # save_cache(self.games)
            # self.load_games(self.games)
        except Exception as e:
            self.log_message(
                f"Error extracting {game.title}: {type(e).__name__}: {e}"
            )

    def extract_game_or_games_package(self):
        if self.overwrite_check.isChecked():
            overwrite = True
        else:
            overwrite = False

        if self.all_checkbox.isChecked():
            games = self.games
        else:
            if (result := self.get_selected_game()) is None:
                return
            game, _ = result
            games = [game]

        self.log_message(f"\nChecking {len(games)} Xbox Live Indie Games\n", "#2ecc71")

        total = len(games)

        for i, game in enumerate(games, 1):
            if game.extracted is not None or not game.package:
                self.log_message_log(f"{game.title} Already Extracted")
                if not overwrite: continue

            self.log_message(f"[{i}/{total}] Extracting {game.title}...")
            self.extract_game(game)

        self.load_games(self.games, refresh_only=True)

    def extract_package(self, game: XBLIGGame):
        package = game.package

        if not package:
            return None

        package = Path(package)

        if not package.exists():
            self.log_message_log(f"Package missing: {package}")
            return None

        from stfs_extract import extract_live_pirs
        assert game.folder_title is not None

        attrs = {
            "decompiled": (
                "decompiled",
                Path(self.config["indie_games_path"]) / "decompiled" / game.title
            ),
            "extracted": (
                "extracted",
                Path(self.config["indie_games_path"]) / "extracted" / game.folder_title
            ),
        }

        attr_name, decompiled = attrs["decompiled"]
        attr_name, extracted_path = attrs["extracted"]

        # extracted_path = package.parent / "extracted"

        extracted_path.mkdir(parents=True, exist_ok=True)
        self.extracted = extracted_path

        try:
            from contextlib import redirect_stdout
            from functools import partial
            func = partial(extract_live_pirs, package, extracted_path, None)
            self.game = game
            self.run_worker(func)
            self.log_message_log(f"Extracted to: {extracted_path}")

        except Exception as e:
            self.log_message(f"Extraction failed for {game.title}: {type(e).__name__}: {e}")
            self.log_message(traceback.format_exc())
            return None

        return extracted_path

    def load_games(self, games: list[XBLIGGame], refresh_only: bool = False,):
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
            self.convert_content_check = QCheckBox("Add To Indie Game Solution")
            self.open_vs_check = QCheckBox("Open Indie Game Solution in Visual Studio.")
            self.open_explorer_check = QCheckBox("Open Decompiled Project Folder.")

            self.convert_csproj_check.setChecked(True)
            self.convert_content_check.setChecked(True)

            self.decompile_check.toggled.connect(self.decompile_cli.setEnabled)
            self.decompile_check.toggled.connect(self.decompile_gui.setEnabled)

            self.decompile_cli.setEnabled(True)
            self.decompile_gui.setEnabled(True)

            # options_layout.addWidget(self.solution_file)
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
            return {
                "decompile": self.decompile_check.isChecked(),
                "decompile_gui": self.decompile_gui.isChecked(),
                "convert_csproj": self.convert_csproj_check.isChecked(),
                "add_to_solution": self.convert_content_check.isChecked(),
                # "convert_content": self.convert_content_check.isChecked(),
                "open_visual_studio": self.open_vs_check.isChecked(),
                "open_explorer": self.open_explorer_check.isChecked(),
            }

    def build_selected(self):
        if (result := self.get_selected_game()) is None:
            return
        game, indexes = result
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
            self.decompile_selected(game, open_explorer=True, use_gui=options["decompile_gui"])

            content_root_dir = game.extracted / "584E07D1"
            copy_extracted_folder_content_and_references(source_content_root_folder=content_root_dir,
                                                         dest_content_folder=game.decompiled,
                                                         dll_files=game.dll_files,
                                                         log_callback=self.log_message)

        # if options["convert_content"]:
        #
        if options["convert_csproj"] or options["add_to_solution"]:
            # if game.decompiled is not None:
            converter = self.method_name()
            csproj_files = get_cs_project_folders([game], self.log_message)
            for project in csproj_files:
                try:
                    converter.convert_project_folder(project, options["add_to_solution"], game.dll_files)
                except Exception as e:
                    self.log_message(f"FAILED {project}: {e}")
        if options["open_visual_studio"]:
            self.log_message("Opening Solution in Visual Studio. The Decompiled Projects Should Have Been Added.")
            if game.decompiled is not None:
                solution = self.config["indie-game-solution-location"]
                os.startfile(solution)
            else:
                self.log_message("Game has not been Decompiled.")

        # folder = game.extracted
        # content_dir = folder / "584E07D1" / "Content"
        # assert game.decompiled is not None
        # copy_content_folder(content_dir, game.decompiled / "Content")
        t = ToolManager()
        t.cleanup()

    def launch_selected(self):
        self.log_message("Launching selected game...")

    def refresh_games(self):
        self.load_games(self.games)

    def open_selected_folder(self, folder="root"):
        if (result := self.get_selected_game()) is None:
            return
        game, index = result
        if folder=="root":
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
        if (result := self.get_selected_game()) is None:
            return
        game, indexes = result
        if game is None or game.title_id is None:
            return

        attrs = {
            "decompiled": (
                "decompiled",
                Path("d/downloads") / "decompiled" / game.title,
                game.decompiled,
            ),
            "extracted": (
                "extracted",
                Path("d/downloads") / "extracted" / game.title,
                game.extracted,
            ),
        }

        attr_name, path, attr_path_value = attrs[files]

        try:
            if path and path.exists():
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
            self.log_message(f"Unable to delete '{path}': {e}")
            return
        self.update_labels(game)
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

        self.create_labels_drawer(form)

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
        self.open_xml_btn = QPushButton("Delete Extracted")
        self.open_xml_btn.clicked.connect(partial(self.delete_game_files, "extracted"))
        self.export_btn = QPushButton("Delete Decompiled")
        self.export_btn.clicked.connect(partial(self.delete_game_files, "decompiled"))

        # actions.addWidget(self.run_btn)
        actions.addWidget(self.validate1_btn)
        actions.addWidget(self.validate2_btn)
        actions.addWidget(self.validate3_btn)
        actions.addWidget(self.open_xml_btn)
        actions.addWidget(self.export_btn)
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

    #
    # title: str
    # icon: Path | None = None
    #
    # folder_title: str | None = None
    # title_id: str | None = None
    # virtual_title_id: str | None = None
    # xml_title_id: str | None = None
    # requested_by: str | None = None
    # publisher: str | None = None
    #
    # content_type: str | None = None
    # content_name: str | None = None
    # content_converted: str = "No"
    # content_format: str = "xnb content"
    #
    # package: Path | None = None
    # extracted: Path | None = None
    # game_root: Path | None = None
    #
    # exe: Path | None = None
    # dll_files: list[Path] = field(default_factory=list)
    # xml: Path | None = None
    # decompiled: Path | None = None
    #
    def create_labels_drawer(self, form: QFormLayout):
        self.title_lbl = QLabel("-")
        self.titleid_lbl = QLabel("-")
        self.dll_files_lbl = QLabel("-")
        self.exe_lbl = QLabel("-")
        self.xml_lbl = QLabel("-")
        self.decompiled_lbl = QLabel("-")
        self.status_lbl = QLabel("-")

        form.addRow("Title", self.title_lbl)
        form.addRow("Title ID", self.titleid_lbl)
        form.addRow("DLL Files", self.dll_files_lbl)
        form.addRow("Executable", self.exe_lbl)
        form.addRow("GameInfo.xml", self.xml_lbl)
        form.addRow("Decompiled", self.decompiled_lbl)
        form.addRow("Status", self.status_lbl)

    def build_ui(self):

        self.scan_btn = QPushButton("Scan Games")
        self.scan_btn.clicked.connect(self.rescan_games_responsive)
        self.extract_btn = QPushButton("Extract Selected Game Package")
        self.extract_btn.clicked.connect(self.extract_game_or_games_package)
        self.build_btn = QPushButton("Decompile Game and Assemblies")
        self.build_btn.clicked.connect(self.build_selected)
        self.convert_project_btn = QPushButton("Convert Game Project")
        self.convert_project_btn.clicked.connect(self.convert_game_project)
        self.open_folder_btn = QPushButton("Open Game Folder")
        self.open_folder_btn.clicked.connect(partial(self.open_selected_folder,"root"))
        self.open_folder_extracted_btn = QPushButton("Open Game Extracted Folder")
        self.open_folder_extracted_btn.clicked.connect(partial(self.open_selected_folder,"extracted"))
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
        button_row.addWidget(self.convert_project_btn)
        button_row.addWidget(self.open_folder_btn)
        button_row.addWidget(self.open_folder_extracted_btn)
        button_row.addWidget(self.compress_btn)
        button_row.addWidget(self.decompress_btn)

        main_layout.addLayout(button_row)

        # -----------------------------
        # Second row - options
        # -----------------------------
        options_row = QHBoxLayout()

        self.all_checkbox = QCheckBox("All or One")
        self.all_checkbox.toggled.connect(self.all_or_one)

        self.overwrite_check = QCheckBox("Overwrite Extract")
        self.cache_check = QCheckBox("Override Cache")

        self.root_edit = QLineEdit()
        self.root_edit.setPlaceholderText("Indie Games Root folder...")
        self.root_edit.setMaximumWidth(500)
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

        self.open_ilspy_btn = QPushButton("Open ILSpy")
        self.open_ilspy_btn.clicked.connect(self.open_ilspy)

        options_row.addWidget(self.all_checkbox)
        options_row.addWidget(self.overwrite_check)
        options_row.addWidget(self.cache_check)
        options_row.addWidget(self.root_edit, 1)
        options_row.addWidget(self.root_browse_btn)
        options_row.addWidget(self.root_solution_edit, 1)
        options_row.addWidget(self.root_solution_browse_btn)

        options_row.addWidget(self.open_ilspy_btn)

        options_row.addStretch()
        self.all_checkbox.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )

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
            QAbstractItemView.SelectionMode.SingleSelection
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

    from contextlib import redirect_stdout
    from io import StringIO

    def open_ilspy(self):
        ensure_tool_extracted("ilspy", log=self.log_message,)
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

    def all_or_one(self, checked):
        self.compress_btn.setText(
            "Compress All Extracted Content"
            if checked
            else "Compress Selected Extracted Content"
        )
        self.extract_btn.setText(
            "Extract All Game Packages"
            if checked
            else "Extract Selected Game Package"
        )
        self.convert_project_btn.setText(
            "Convert Game Projects"
            if checked
            else "Convert Game Project"
        )
        self.decompress_btn.setText(
            "Decompress All Extracted Content"
            if checked
            else "Decompress Selected Extracted Content"
        )

    from html import escape

    # def log_message(self, message, color=None):
    #     message = escape(str(message))
    #
    #     if color:
    #         message = f'<span style="color: {color};">{message}</span>'
    #
    #     self.log_window.appendHtml(message)

    def log_message(self, message, color=None):
        message = escape(str(message))

        if color is None:
            color = RAINBOW_COLORS[self._rainbow_index]
            self._rainbow_index = (
                                          self._rainbow_index + 1
                                  ) % len(RAINBOW_COLORS)

        self.log_window.appendHtml(
            f'<span style="color: {color};">{message}</span>'
        )

RAINBOW_COLORS = [
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

if __name__ == "__main__":
    setup_logger()

    app = QApplication(sys.argv)
    xbdlg = XBLIGDialog()
    xbdlg.exec()

    # cleanup_nested_categories(r"C:\PycharmProjects\xenia-game-manager\src\downloads")
    #
    # move_folders_to_type(get_app_dir() / "downloads")
    #
    # exe = Path(get_app_dir() / "downloads" / "XBLIG" / "Alien Jelly (World) (XBLIG)/584E07D2/00000002/62F2648203AAB1C526B538091DF3BBE8CFC6E7E758_extracted/584E07D1/Game.exe")
    # if exe.exists(): read_bytes(exe)
