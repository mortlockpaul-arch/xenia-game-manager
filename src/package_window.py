import json
import logging
import random
import shutil
import subprocess
import threading
from contextlib import redirect_stdout
from functools import partial
from xml.etree import ElementTree as ET

import time
from dataclasses import dataclass, asdict
from typing import cast

import sys
from PySide6.QtGui import QFont

from config import get_app_dir
from pathlib import Path
import xml.etree.ElementTree as ET

from line_profiler_pycharm import profile
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QRect, QThread, Signal, QObject
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
    QHeaderView, QApplication, QMessageBox, QSizePolicy, QFrame, QGraphicsDropShadowEffect, QCheckBox, QButtonGroup,
    QRadioButton, QProgressBar, QPlainTextEdit,
)

from convert_xna_projects import FNA_VERSION

from dataclasses import dataclass
from pathlib import Path


@dataclass
class ConversionResult:
    tool: str
    success: bool
    input_file: Path
    output_files: list[Path]
    stdout: str
    stderr: str
    error: str | None = None

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

from pathlib import Path
import subprocess
DECOMPILER = get_app_dir() / "assets" / "tools" / "decompiler"

ILSPY_GUI = DECOMPILER / "ILSpy" / "publish" / "ILSpy.exe"
ILSPY_CMD = DECOMPILER / "ILSpyCmd" / "publish" / "ilspycmd.exe"
from PySide6.QtCore import QProcess

from PySide6.QtCore import QProcess


def decompile_project(
    exe: Path,
    parent=None,
) -> tuple[Path, ToolManager, QProcess]:

    tools = ToolManager("decompiler")
    tools.extract()

    output_dir = exe.parent.parent.parent / "decompiled"
    output_dir.mkdir(parents=True, exist_ok=True)



    if not exe.exists():
        tools.cleanup()
        raise FileNotFoundError(f"ILSpy executable not found: {ilspy}")

    process = QProcess(parent)

    arguments = [
        str(exe),
        "-p",
        "-o",
        str(output_dir),
    ]

    process.start(
        str(exe),
        arguments,
    )

    return output_dir, tools, process

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

def compress_tools_folder(
        tools_dir: Path,
        archive: Path | None = None,
        delete_original: bool = False,
) -> Path:

    tools_dir = Path(tools_dir)

    if archive is None:
        archive = tools_dir.with_suffix(".7z")

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
            str(tools_dir),
        ],
        check=True,
    )

    if delete_original:
        shutil.rmtree(tools_dir)

    return archive

def ensure_tool_extracted(name: str) -> Path:
    tools_root = get_app_dir() / "assets" / "tools"
    folder = tools_root / name
    archive = tools_root / f"{name}.7z"

    if folder.exists():
        return folder

    subprocess.run(
        [
            str(get_7zip()),
            "x",
            str(archive),
            f"-o{tools_root}",
            "-y",
        ],
        check=True,
    )

    if not folder.exists():
        raise RuntimeError(f"Failed to extract tool '{name}'")

    return folder

from pathlib import Path
import shutil
import subprocess

def compress_tool(name: str):
    tools_root = get_app_dir() / "assets" / "tools"

    folder = tools_root / name
    archive = tools_root / f"{name}.7z"

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
            str(folder),
        ],
        check=True,
    )


def cleanup_tool(name: str):
    tools_root = get_app_dir() / "assets" / "tools"
    folder = tools_root / name

    if folder.exists():
        shutil.rmtree(folder)

class ToolManager:

    def __init__(self, *tools: str):
        self.tools = tools

    def extract(self):
        for tool in self.tools:
            ensure_tool_extracted(tool)

    def cleanup(self):
        for tool in self.tools:
            cleanup_tool(tool)

    def __enter__(self):
        self.extract()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.cleanup()

class ConvertXnaProjects(QObject):

    log_signal = Signal(str)
    progress_signal = Signal(int)
    finished_signal = Signal(object)

    def __init__(self, project_path, games, /):
        super().__init__()
        self.project_path = Path(project_path)
        self.games = games

    from pathlib import Path
    import shutil
    import subprocess


    def log_message(self, message):
        self.log_signal.emit(message)

    def find_xblig_packages(self, root: str | Path):

        root = Path(root)
        games: list[XBLIGGame] = []

        STFS_MAGIC = {
            b"CON ",
            b"LIVE",
            b"PIRS",
        }

        def is_stfs(path: Path) -> bool:
            try:
                with path.open("rb") as f:
                    return f.read(4) in STFS_MAGIC
            except Exception:
                return False

        def parse_xml(xml_file: Path) -> dict:

            if not xml_file.exists():
                return {}

            try:
                tree = ET.parse(xml_file)
                title_info = tree.getroot().find(".//TitleInfo")

                if title_info is None:
                    return {}

                return {
                    "title": title_info.attrib.get("Name"),
                    "virtual_title_id": title_info.attrib.get("VirtualTitleID"),
                    "xml_title_id": title_info.attrib.get("TitleID"),
                    "image_path": title_info.attrib.get("ImagePath"),
                }

            except Exception as e:
                self.log_signal.emit(f"XML error: {xml_file} ({e})")
                return {}

        #
        # Phase 1 - Find STFS packages
        #

        self.log_signal.emit("Scanning for STFS packages...")

        all_files = [p for p in root.rglob("*") if p.is_file()]
        total_files = len(all_files)

        packages = []
        last_progress = -1

        for i, path in enumerate(all_files, start=1):

            progress = int(i * 40 / max(total_files, 1))

            if progress != last_progress:
                self.progress_signal.emit(progress)
                last_progress = progress

            if is_stfs(path):
                packages.append(path)

        self.log_signal.emit(f"Found {len(packages)} STFS package(s).")

        #
        # Phase 2 - Build game list
        #

        total_packages = len(packages)
        last_progress = -1

        for index, package in enumerate(packages, start=1):

            progress = 40 + int(index * 60 / max(total_packages, 1))

            if progress != last_progress:
                self.progress_signal.emit(progress)
                last_progress = progress

            folder_title = package.parents[2].name if len(package.parents) >= 3 else package.parent.name

            title_id = package.parent.parent.name if package.parent.parent else None
            content_type = package.parent.name

            extracted = package.parent / "extracted"
            game_info = extracted / "GameInfo.xml"
            decompiled = extracted / "decompiled"

            xml_data = parse_xml(game_info)

            title = (
                    xml_data.get("title")
                    or folder_title
                    or package.stem
            )

            exe_file = (
                next(extracted.rglob("*.exe"), None)
                if extracted.exists()
                else None
            )

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
                    decompiled=decompiled if decompiled.exists() else None,
                )
            )

            #
            # Don't spam the log.
            #
            if index % 25 == 0 or index == total_packages:
                self.log_signal.emit(
                    f"Processed {index}/{total_packages} package(s)..."
                )

        self.progress_signal.emit(100)

        self.log_signal.emit("")
        self.log_signal.emit("===================")
        self.log_signal.emit(f"Scanner found {len(games)} XBLIG game(s).")

        return games

    def convert_xnb_folder_tools(self, game: XBLIGGame, tool_id: int = 1):

        if game.extracted is None:
            self.log_signal.emit(f"Game not extracted: {game}")
            return None

        content_dir = game.extracted / "584E07D1" / "Content"
        output_dir = content_dir.parent / "Content_Output"

        if not content_dir.exists():
            self.log_signal.emit(f"Content folder not found: {content_dir}")
            return None

        alba = (
                get_app_dir()
                / "assets/tools/conversion/Alba.XnaConvert.0.1.2/Alba.XnaConvert.exe"
        )

        xnb_cli = (get_app_dir() / "assets/tools/conversion/xnbcli-windows-x64/xnbcli.exe")

        xnb_extractor = Path("C:/xnb-extractor/bin/x86/Debug/net481/XnbExtractor.exe")

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
                "--output",str(output_dir),
                "--loader",
                "--parser",
                "--dds",
                "--overwrite",
            ]
        else:
            self.log_signal.emit(f"Unknown tool id: {tool_id}")
            return None

        self.log_signal.emit(f"Running {tool_name}...")

        try:
            stdout_lines = []
            stderr_lines = []

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
                    self.log_signal.emit(line)

                for line in process.stderr:
                    line = line.rstrip()
                    stderr_lines.append(line)
                    self.log_signal.emit(f"ERR: {line}")

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

            self.log_signal.emit(
                f"{tool_name}: {'SUCCESS' if success else 'FAILED'}"
            )

            self.log_signal.emit(
                f"Generated files: {len(output_files)}"
            )

            if not success:
                failed_folders.append(content_dir)

            self.finished_signal.emit(result)

        except Exception as e:

            failed_folders.append(content_dir)

            self.log_signal.emit(
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

        self.log_signal.emit("")
        self.log_signal.emit("===================")
        self.log_signal.emit("Conversion complete")
        self.log_signal.emit(
            f"Failed folders: {len(failed_folders)}"
        )

        for folder in failed_folders:
            self.log_signal.emit(str(folder))

        return result


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
    from pathlib import Path
    import xml.etree.ElementTree as ET

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
        self.setWindowTitle("XBLIG Rebuilder")
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

        converter = ConvertXnaProjects(get_app_dir(), self.games)

        converter.log_signal.connect(self.log_message_log)
        converter.progress_signal.connect(self.progress_bar.setValue)
        converter.finished_signal.connect(self.tool_finished)

        converter.convert_project_single_folder(decompiled)

    def convert_folders(self):
        game = self.get_selected_game()
        root = get_app_dir() / "downloads" / "XBLIG"
        converter = ConvertXnaProjects(get_app_dir(), self.games)

        converter.log_signal.connect(self.log_message_log)
        converter.progress_signal.connect(self.progress_bar.setValue)
        converter.finished_signal.connect(self.tool_finished)

        converter.convert_projects_all_folders(root)

    def run_in_background(self, func, *args):
        threading.Thread(
            target=func,
            args=args,
            daemon=True,
        ).start()

    def convert_content(self, tool_id=1):
        self.validate1_btn.setDisabled(True)
        self.validate2_btn.setDisabled(True)
        self.validate3_btn.setDisabled(True)
        game = self.get_selected_game()
        if game:
            with ToolManager("conversion"):
                converter = ConvertXnaProjects(get_app_dir(), self.games)

                converter.log_signal.connect(self.log_message_log)
                converter.progress_signal.connect(self.progress_bar.setValue)
                converter.finished_signal.connect(self.tool_finished)

                self.progress_bar.setRange(0, 0)  # Busy animation
                self.run_in_background(converter.convert_xnb_folder_tools, game, tool_id)

    def tool_finished(self, result: ConversionResult):
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)

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

    def decompile_selected(self, game: XBLIGGame, open_explorer: bool = True, use_gui=False):

        exe = game.exe

        if not exe:
            QMessageBox.warning(self, "No Executable", "Extract the game first.")
            return

        self.log_message(f"Generating Visual Studio project for {exe.name}...")

        try:
            exe = ILSPY_GUI if use_gui else ILSPY_CMD
            project_dir, tools, process = decompile_project(
                exe,
                parent=self,
            )

            self.ilspy_process = process
            game.decompiled = project_dir

            if process is not None:
                # Async GUI/QProcess mode
                process.finished.connect(
                    lambda *_: self.on_decompile_finished(project_dir, tools)
                )
            else:
                # CLI mode already completed
                self.on_decompile_finished(project_dir, tools)

        except subprocess.CalledProcessError as e:
            QMessageBox.critical(self, "ILSpy", str(e))
            return

        if open_explorer:
            subprocess.Popen(["explorer", str(project_dir)])

    def on_decompile_finished(self, project_dir, tools):
        tools.cleanup()
        print(f"Decompiled project: {project_dir}")

    from PySide6.QtCore import QObject, QThread, Signal

    class ScanWorker(QObject):

        finished_signal = Signal(list)
        log_signal = Signal(str)
        progress_signal = Signal(int)

        def __init__(self, root: Path, converter: ConvertXnaProjects, force=False):
            super().__init__()

            self.root = root
            self.converter = converter
            self.force = force

            # Forward converter signals
            # self.converter.log_signal.connect(self.log_signal)
            # self.converter.progress_signal.connect(self.progress_signal)

        from pathlib import Path

        def run(self):

            try:
                self.log_signal.emit("Checking game cache...")

                games:list[XBLIGGame] = []
                current_mtime = get_folder_mtime(self.root)
                cache = None if self.force else load_cache()

                if cache and cache.get("mtime") == current_mtime:
                    games = cache["games"]
                    self.log_signal.emit(f"Loaded {len(games)} games from cache.")
                    self.progress_signal.emit(100)
                else:
                    self.log_signal.emit("Scanning folders...")
                    if not self.root.exists():
                        self.log_signal.emit(f"Folder {self.root} does not exist.")
                        self.progress_signal.emit(100)
                    else:
                        games = self.converter.find_xblig_packages(self.root)
                        save_cache(games)
                        self.log_signal.emit("Cache updated.")
                self.finished_signal.emit(games)

            except Exception as e:
                self.log_signal.emit(f"Scanner error: {e}")
                self.finished_signal.emit([])

    def rescan_games_responsive(self, force=False):
        root = get_app_dir() / "downloads" / "XBLIG"

        converter = ConvertXnaProjects(get_app_dir(), self.games)

        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

        self.scan_btn.setEnabled(False)

        self.thread = QThread(self)

        self.worker = self.ScanWorker(root, converter, force)

        converter.log_signal.connect(self.worker.log_signal)
        converter.progress_signal.connect(self.worker.progress_signal)

        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)

        self.worker.log_signal.connect(self.log_message_log)
        self.worker.progress_signal.connect(self.progress_bar.setValue)
        self.worker.finished_signal.connect(self.scan_finished)

        self.worker.finished_signal.connect(self.thread.quit)
        self.worker.finished_signal.connect(self.worker.deleteLater)
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
        self.rescan_games_responsive(force=True)

    def log_message(self, message):
        self.log_window.appendPlainText(message)

    def log_message_log(self, message):
        self.log_message(message)
        logging.info(f"{message}")

    def extract_xblig_package(self, game: XBLIGGame):
        package = game.package

        if not package:
            return None

        package = Path(package)

        if not package.exists():
            self.log_message_log(f"Package missing: {package}")
            return None

        from stfs_extract import extract_live_pirs

        # Create extracted folder beside package
        extracted_path = package.parent / "extracted"

        extracted_path.mkdir(parents=True, exist_ok=True)

        try:
            from contextlib import redirect_stdout

            with redirect_stdout(QtLogger(self.log_message_log)):
                extract_live_pirs(package, extracted_path)

            self.log_message_log(f"Extracted to: {extracted_path}")

        except Exception as e:
            self.log_message_log(f"Extraction failed: {e}")
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

            self.convert_csproj_check = QCheckBox("Convert project (.csproj)")
            self.convert_content_check = QCheckBox("Convert XNA content")
            self.open_vs_check = QCheckBox("Open project in Visual Studio")
            self.open_explorer_check = QCheckBox("Open project folder in Explorer")

            self.convert_csproj_check.setChecked(True)
            self.convert_content_check.setChecked(True)

            self.decompile_check.toggled.connect(self.decompile_cli.setEnabled)
            self.decompile_check.toggled.connect(self.decompile_gui.setEnabled)

            self.decompile_cli.setEnabled(True)
            self.decompile_gui.setEnabled(True)

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
            self.decompile_selected(game, open_explorer=True,use_gui=options["decompile_gui"])

            assert game.decompiled is not None
            content_dir = game.extracted / "584E07D1" / "Content"
            copy_content_folder(content_dir, game.decompiled / "Content",)
            
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
        game: XBLIGGame | None = self.get_selected_game()

        if not game or not game.game_root or not game.game_root.exists():
            self.log_message("No valid game folder selected.")
            return

        subprocess.Popen(["explorer", str(game.game_root)])
        self.log_message(f"Opened: {game.game_root}")

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

    from pathlib import Path
    import shutil

    def delete_game_files(self, files: str):
        game = self.get_selected_game()
        if game is None:
            return

        attrs = {
            "decompiled": "decompiled",
            "extracted": "extracted",
        }

        attr = attrs.get(files)
        if attr is None:
            return

        path = getattr(game, attr)

        try:
            if path and path.exists():
                shutil.rmtree(path)
                self.log_message(f"Deleted: {path}")

            setattr(game, attr, None)

        except PermissionError as e:
            self.log_message(f"Unable to delete '{path}': {e}")
            return

        self.load_games(self.games)

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
        # self.run_btn = QPushButton("Launch Game")
        self.validate1_btn = QPushButton("Convert Content (xnb-cli)")
        self.validate1_btn.clicked.connect(lambda: self.convert_content(tool_id=2))

        self.validate2_btn = QPushButton("Convert Content (xna-convert)")
        self.validate2_btn.clicked.connect(lambda: self.convert_content(tool_id=1))


        self.validate3_btn = QPushButton("Convert Content (xnb-extractor)")
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

        self.convert_all_btn = QPushButton("Convert Game")
        self.convert_all_btn.clicked.connect(self.convert_folders)
        #
        self.launch_btn = QPushButton("Launch Game")
        self.launch_btn.clicked.connect(self.launch_selected)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_games)
        #
        self.open_folder_btn = QPushButton("Open Folder")
        self.open_folder_btn.clicked.connect(self.open_selected_folder)

        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.close)

        toolbar.addWidget(self.scan_btn)
        toolbar.addWidget(self.extract_btn)
        toolbar.addWidget(self.build_btn)
        toolbar.addWidget(self.convert_all_btn)
        toolbar.addWidget(self.launch_btn)
        toolbar.addWidget(self.open_folder_btn)
        toolbar.addWidget(self.refresh_btn)
        toolbar.addWidget(self.close_btn)
        toolbar.addWidget(self.random_btn)
        toolbar.addStretch()

        main_layout.addLayout(toolbar)

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

        from PySide6.QtWidgets import QTextEdit

        self.log_window = QPlainTextEdit()
        self.log_window.setReadOnly(True)
        self.log_window.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.log_window.setFont(QFont("Consolas", 9))

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


