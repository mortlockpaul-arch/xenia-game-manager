import logging
import random
import threading
import traceback
import xml.etree.ElementTree as ET  # noqa: N812
from contextlib import redirect_stdout
from dataclasses import dataclass
from dataclasses import field
from functools import partial
from pathlib import Path

import sys
import time
from typing import Any, Callable

from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QRect, QThread, Signal, QObject, QModelIndex, \
    Slot
from PySide6.QtGui import QFont
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
    QFormLayout,
    QGroupBox,
    QHeaderView, QApplication, QMessageBox, QSizePolicy, QFrame, QGraphicsDropShadowEffect, QCheckBox, QButtonGroup,
    QRadioButton, QProgressBar, QPlainTextEdit, QLineEdit,
)

from config import get_app_dir
from convert_xna_projects import FNA_VERSION
from logging_setup import setup_logger


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

import os


def open_solution(project_dir: Path):
    for csproj in project_dir.glob("*.csproj"):
        os.startfile(csproj)
        return


DECOMPILER = get_app_dir() / "assets" / "tools"

ILSPY_GUI = DECOMPILER / "ILSpy" / "publish" / "ILSpy.exe"
ILSPY_CMD = DECOMPILER / "ILSpyCmd" / "Release" / "net10.0" / "ilspycmd.exe"

from PySide6.QtCore import QProcess


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
    dll_files: list[Path] = field(default_factory=list)
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

            elif isinstance(value, list):
                value = [
                    str(item) if isinstance(item, Path) else item
                    for item in value
                ]

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

            elif field.name == "dll_files" and value:
                value = [Path(x) for x in value]

            converted[field.name] = value

        return cls(**converted)


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

    if dest_content_folder.exists() and dest_content_folder.is_dir():
        shutil.rmtree(dest_content_folder)

    shutil.copytree(source_content_root_folder, dest_content_folder)

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


def ensure_tool_extracted(name: str):
    tools_root = get_app_dir() / "assets" / "tools"

    relative_path = TOOL_PATHS[name]
    folder = tools_root / relative_path
    archive = tools_root / f"{name}.7z"

    if folder.exists():
        return

    if not archive.exists():
        raise FileNotFoundError(
            f"Tool archive not found: {archive}"
        )

    folder.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [
            str(get_7zip()),
            "x",
            str(archive),
            "-y",
        ],
        cwd=folder,
        check=True,
    )


from pathlib import Path
import shutil
import subprocess


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


def cleanup_tool(name: str):
    tools_root = get_app_dir() / "assets" / "tools"

    relative_path = get_tool_path(name)
    folder = tools_root / relative_path

    if not folder.exists():
        return

    try:
        shutil.rmtree(folder)
        print(f"Cleaned up: {folder}")
    except PermissionError as e:
        print(f"Cleanup failed for {folder}: {e}")


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


def get_cs_project_folders(games: list[XBLIGGame]) -> list[Path]:
    projects = []
    for game in games:
        if game.decompiled is None:
            continue
        projects.extend(p for p in game.decompiled.rglob("*.csproj"))
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
    log_signal = Signal(str)
    progress_signal = Signal(int)
    total_files_signal = Signal(int)
    finished_signal = Signal(ConversionResult)

    def __init__(self, project_path, games, options, /):
        super().__init__()

        self.options: dict[str, QCheckBox] = options
        self.project_path = Path(project_path)
        self.games = games

    def log_message(self, message):
        self.log_signal.emit(message)

    from pathlib import Path

    def find_packages(self, root: str | Path):
        root = Path(root)
        games: list[XBLIGGame] = []
        stfs_magic = {b"CON ", b"LIVE", b"PIRS"}

        def is_stfs(path: Path) -> bool:
            try:
                with path.open("rb") as f:
                    return f.read(4) in stfs_magic
            except OSError:
                return False

        def scan_files(folder: Path):
            try:
                with os.scandir(folder) as entries:
                    for entry in entries:
                        try:
                            if entry.is_file(follow_symlinks=False):
                                yield Path(entry.path)
                            elif entry.is_dir(follow_symlinks=False):
                                yield from scan_files(Path(entry.path))
                        except OSError:
                            continue
            except OSError:
                return

        def parse_xml(xml_file: Path) -> dict:
            if not xml_file.exists():
                return {}

            try:
                title_info = ET.parse(xml_file).getroot().find(".//TitleInfo")

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

        self.log_signal.emit("Scanning for STFS packages...")

        packages = []
        files_scanned = 0
        last_progress = -1
        files = list(scan_files(root))
        total_files = len(files)

        self.total_files_signal.emit(total_files)

        files_scanned = 0

        for path in files:
            files_scanned += 1

            # Progress during the initial scan is only approximate.
            if files_scanned % 5 == 0:
                self.progress_signal.emit(files_scanned)

            if is_stfs(path):
                packages.append(path)

        self.log_signal.emit(
            f"Found {len(packages)} STFS package(s)."
        )

        total_packages = len(packages)

        for index, package in enumerate(packages, start=1):
            progress = int(index * 5 / max(total_packages, 1))

            if progress != last_progress:
                self.progress_signal.emit(progress)
                last_progress = progress

            folder_title = (
                package.parents[2].name
                if len(package.parents) >= 3
                else package.parent.name
            )

            attrs = {
                "decompiled": (
                    "decompiled",
                    Path("D:/downloads") / "decompiled" / folder_title
                ),
                "extracted": (
                    "extracted",
                    Path("D:/downloads") / "extracted" / folder_title
                ),
            }

            attr_name, decompiled = attrs["decompiled"]
            attr_name, extracted = attrs["extracted"]
            game_info = extracted / "GameInfo.xml"
            title_id = package.parent.parent.name
            xml_data = parse_xml(game_info)
            title = xml_data.get("title") or folder_title or package.stem
            decompiled_path_value = package.parent / "decompiled"
            extracted_path_value = package.parent / "extracted"

            profile_string = decompiled / "Microsoft.Xna.Framework.RuntimeProfile"

            content_format = (
                profile_string.read_text().strip()
                if profile_string.exists()
                else ""
            )

            exe_file = None
            dll_files = []

            if extracted.exists():
                for path in scan_files(extracted):
                    suffix = path.suffix.lower()

                    if suffix == ".exe" and exe_file is None:
                        exe_file = path

                    elif suffix == ".dll":
                        dll_files.append(path)

            self.log_signal.emit(f"Processed {title}")

            games.append(
                XBLIGGame(
                    title=title,
                    folder_title=folder_title,
                    title_id=title_id,
                    virtual_title_id=xml_data.get("virtual_title_id"),
                    xml_title_id=xml_data.get("xml_title_id"),
                    content_type=content_format,
                    content_name="Xbox Live Indie Game",
                    content_format=content_format,
                    package=package,
                    extracted=extracted if extracted.exists() else extracted_path_value if extracted_path_value.exists() else None,
                    game_root=extracted if extracted.exists() else package.parent,
                    exe=exe_file,
                    dll_files=dll_files,
                    xml=game_info if game_info.exists() else None,
                    decompiled=decompiled if decompiled.exists() else decompiled_path_value if decompiled_path_value.exists() else None,
                )
            )

            self.log_signal.emit(
                f"Processed {index}/{total_packages} package(s)..."
            )

        self.progress_signal.emit(100)

        self.log_signal.emit("")
        self.log_signal.emit("===================")
        self.log_signal.emit(
            f"Scanner found {len(games)} XBLIG game(s)."
        )

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
            self.log_signal.emit(f"Unknown tool id: {tool_id}")
            return None

        self.log_signal.emit(f"Running {tool_name}...")

        try:
            stdout_lines = []
            stderr_lines = []

            self.log_signal.emit("Full command:")
            self.log_signal.emit(" ".join(cmd))

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

    from pathlib import Path
    import xml.etree.ElementTree as ET

    def clean_csproj(self, project_path: Path) -> None:
        project_path = Path(project_path)

        self.log_message(f"Updating project: {project_path.name}")
        self.log_message(f"  Project path: {project_path}")

        tree = ET.parse(project_path)
        root = tree.getroot()

        # ---------------------------------------------------------
        # MSBuild namespace handling
        # ---------------------------------------------------------

        ns = ""

        if root.tag.startswith("{"):
            ns = root.tag.split("}")[0] + "}"

        def tag(name: str) -> str:
            return f"{ns}{name}"

        self.log_message("  Reading existing project properties...")

        # ---------------------------------------------------------
        # Preserve AssemblyName
        # ---------------------------------------------------------

        assembly_name = None

        for propgroup in root.findall(tag("PropertyGroup")):
            assembly = propgroup.find(tag("AssemblyName"))

            if assembly is not None and assembly.text:
                assembly_name = assembly.text.strip()
                break

        if assembly_name:
            self.log_message(
                f"  Preserving AssemblyName: {assembly_name}"
            )
        else:
            self.log_message(
                "  No AssemblyName found; project will use the default."
            )

        # ---------------------------------------------------------
        # Remove existing PropertyGroups / ItemGroups
        # ---------------------------------------------------------

        removed_property_groups = 0
        removed_item_groups = 0

        for element in list(root):
            local_name = element.tag.split("}")[-1]

            if local_name == "PropertyGroup":
                root.remove(element)
                removed_property_groups += 1

            elif local_name == "ItemGroup":
                root.remove(element)
                removed_item_groups += 1

        self.log_message(
            f"  Removed {removed_property_groups} existing "
            f"PropertyGroup(s)."
        )

        self.log_message(
            f"  Removed {removed_item_groups} existing "
            f"ItemGroup(s), including old XNA references."
        )

        # ---------------------------------------------------------
        # Create clean PropertyGroup
        # ---------------------------------------------------------

        self.log_message("  Creating clean project properties...")

        propgroup = ET.SubElement(
            root,
            tag("PropertyGroup")
        )

        if assembly_name:
            ET.SubElement(
                propgroup,
                tag("AssemblyName")
            ).text = assembly_name

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
            ET.SubElement(
                propgroup,
                tag(name)
            ).text = value

            self.log_message(
                f"    {name} = {value}"
            )

        # ---------------------------------------------------------
        # Contents.csproj ProjectReference
        # ---------------------------------------------------------

        content_project = Path(
            r"C:\source\Content-References\Contents.csproj"
        )

        self.log_message(
            f"  Adding project reference: {content_project}"
        )

        itemgroup = ET.SubElement(
            root,
            tag("ItemGroup")
        )

        project_reference = ET.SubElement(
            itemgroup,
            tag("ProjectReference"),
            {
                "Include": str(content_project)
            }
        )

        ET.SubElement(
            project_reference,
            tag("Private")
        ).text = "True"

        ET.SubElement(
            project_reference,
            tag("CopyLocalSatelliteAssemblies")
        ).text = "True"

        self.log_message(
            "    Private = True"
        )

        self.log_message(
            "    CopyLocalSatelliteAssemblies = True"
        )

        # ---------------------------------------------------------
        # Content files
        # ---------------------------------------------------------

        self.log_message(
            r"  Configuring Content\**\* to always copy to output..."
        )

        itemgroup = ET.SubElement(
            root,
            tag("ItemGroup")
        )

        none = ET.SubElement(
            itemgroup,
            tag("None"),
            {
                "Update": r"Content\**\*"
            }
        )

        ET.SubElement(
            none,
            tag("CopyToOutputDirectory")
        ).text = "Always"

        # ---------------------------------------------------------
        # Save
        # ---------------------------------------------------------

        ET.indent(tree, space="\t")

        tree.write(
            project_path,
            encoding="utf-8",
            xml_declaration=True
        )

        self.log_message(
            f"  Project updated successfully: {project_path.name}"
        )

    import os
    from pathlib import Path
    import xml.etree.ElementTree as ET

    def add_project_to_solution(
            self,
            solution_path: Path,
            project_path: Path,
    ) -> bool:
        solution_path = Path(solution_path).resolve()
        project_path = Path(project_path).resolve()

        self.log_message(
            f"Adding project to solution: {project_path.name}"
        )

        if not solution_path.exists():
            self.log_message(
                f"  Solution not found: {solution_path}"
            )
            return False

        if not project_path.exists():
            self.log_message(
                f"  Project not found: {project_path}"
            )
            return False

        tree = ET.parse(solution_path)
        root = tree.getroot()

        # ---------------------------------------------------------
        # Determine project path
        # ---------------------------------------------------------

        if solution_path.drive.lower() == project_path.drive.lower():
            relative_path = os.path.relpath(
                project_path,
                solution_path.parent,
            ).replace("\\", "/")

            project_path_value = relative_path

            self.log_message(
                f"  Using relative project path: {project_path_value}"
            )

        else:
            # Different drives cannot have a relative Windows path.
            project_path_value = project_path.as_posix()

            self.log_message(
                "  Project is on a different drive from the solution."
            )

            self.log_message(
                f"  Using absolute project path: {project_path_value}"
            )

        # ---------------------------------------------------------
        # Check for existing project
        # ---------------------------------------------------------

        for project in root.iter("Project"):
            existing_path = project.get("Path")

            if not existing_path:
                continue

            existing_path_obj = Path(existing_path)

            if not existing_path_obj.is_absolute():
                existing_path_obj = (
                        solution_path.parent / existing_path_obj
                )

            try:
                existing_path_obj = existing_path_obj.resolve()
            except OSError:
                continue

            if existing_path_obj == project_path:
                self.log_message(
                    "  Project is already in the solution."
                )
                return False

        # ---------------------------------------------------------
        # Find indie-game-archive folder
        # ---------------------------------------------------------

        folder = None

        for element in root.findall("Folder"):
            if element.get("Name") == "/indie-game-archive/":
                folder = element
                break

        if folder is None:
            self.log_message(
                "  Creating /indie-game-archive/ solution folder."
            )

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

        # ---------------------------------------------------------
        # Save
        # ---------------------------------------------------------

        ET.indent(tree, space="  ")

        tree.write(
            solution_path,
            encoding="utf-8",
            xml_declaration=False,
        )

        self.log_message(
            f"  Added project to solution: {project_path.name}"
        )

        return True

    def convert_project_folder(self, path_to_csproj_file: Path, add_to_solution=True):
        try:
            # backup project
            # if (folder.parent.parent / "decompiled_backup").exists():
            #     shutil.rmtree(folder.parent.parent / "decompiled_backup")
            # shutil.copytree(folder.parent, folder.parent.parent / "decompiled_backup")
            self.clean_csproj(path_to_csproj_file)

            if add_to_solution:
                solution_path = Path(r"C:\source\Indie-Games\Indie-Games.slnx")
                self.add_project_to_solution(
                    solution_path,
                    path_to_csproj_file,
                )

            # add_xna_compat(folder.parent)
            # self.remove_xna_usings(folder.parent)

        except Exception as e:
            self.log_signal.emit(f"FAILED {path_to_csproj_file}: {e}")

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

    def __init__(self, function: Callable[..., None], *args, **kwargs,):
        super().__init__()
        self.function = function
        self.args = args
        self.kwargs = kwargs
    @Slot()
    def run(self):
        with redirect_stdout(QtLogger(self.log.emit)):
            self.function(*self.args, **self.kwargs)
            self.finished.emit()

class XBLIGDialog(QDialog):

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

        self.build_ui()
        self.create_settings_drawer()
        self.apply_style()

        import logging

    def print_games(self):
        for i, game in enumerate(self.games, 1):
            print("=" * 80)
            print(f"Game #{i}")
            print("=" * 80)

            for key, value in game.items():
                label = key.replace("_", " ").title()
                print(f"{label:<15}: {value}")

            print()

    def get_selected_game(self) -> tuple[XBLIGGame, list[QModelIndex]] | None:
        indexes = self.game_table.selectionModel().selectedRows()

        if not indexes:
            return None

        row = indexes[0].row()

        return self.games[row], indexes

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

        converter.log_signal.connect(self.log_message_log)
        converter.progress_signal.connect(self.progress_bar.setValue)
        converter.finished_signal.connect(self.tool_finished)
        return converter

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

        projects = get_cs_project_folders(games)

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
            ensure_tool_extracted("conversion")
            converter = ConvertXnaProjects(get_app_dir(), self.games, self.options)
            converter.log_signal.connect(self.log_message_log)
            converter.progress_signal.connect(self.progress_bar.setValue)
            converter.finished_signal.connect(self.tool_finished)

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
        cleanup_tool("conversion")
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

    def decompile_project(self, game: XBLIGGame, dll_files: list[Path], ilspy_exe: Path, parent=None, extracted=None,
                          use_gui=False) -> tuple[Path, QProcess]:

        if use_gui:
            ensure_tool_extracted("ilspy")
        else:
            ensure_tool_extracted("ilspycmd")

        attrs = {
            "decompiled": (
                "decompiled",
                Path("D:/downloads") / "decompiled" / game.title
            ),
            "extracted": (
                "extracted",
                Path("D:/downloads") / "extracted" / game.title
            ),
        }

        attr_name, decompiled = attrs["decompiled"]
        attr_name, extracted = attrs["extracted"]

        output_dir = decompiled
        output_dir.mkdir(parents=True, exist_ok=True)

        self.log_message(f"Output Folder: {output_dir}")
        self.log_message(f"ILSpy: {ilspy_exe}")
        assert game.exe is not None
        arguments = [
            str(game.exe),
            "-p",
            "-o",
            str(output_dir),
            "--nested-directories",
        ]

        process = QProcess(parent)

        process.setProgram(str(ilspy_exe))
        process.setArguments(arguments)

        if extracted:
            process.setWorkingDirectory(str(extracted))

        self.log_message(f"Command: {ilspy_exe} {' '.join(arguments)}")
        self.log_message(
            f"Working directory: {process.workingDirectory()}"
        )
        return output_dir, process

    def decompile_selected(self, game: XBLIGGame, open_explorer: bool = True, use_gui=False, ):
        exe = game.exe
        dlls = game.dll_files
        extracted = game.extracted

        if not exe:
            QMessageBox.warning(
                self,
                "No Executable",
                "Extract the game first.",
            )
            return None

        self.log_message(
            f"Generating Visual Studio project for {exe.name}..."
        )

        try:
            ilspy_exe = ILSPY_GUI if use_gui else ILSPY_CMD

            project_dir, process = self.decompile_project(game, dlls, ilspy_exe=ilspy_exe, parent=self,
                                                          extracted=extracted, use_gui=use_gui)

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
                    f"ILSpy started: {exe.name}"
                )
            )

            process.finished.connect(
                lambda exit_code, exit_status:
                self.on_decompile_finished(
                    open_explorer,
                    project_dir,
                    game,
                    exit_code,
                    exit_status,
                )
            )

            self.log_message("Starting ILSpy...")
            process.start()
            return project_dir
        except Exception as e:
            self.log_message(
                f"ERROR decompiling {exe.name}: "
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

    from PySide6.QtCore import QObject

    class ScanWorker(QObject):

        finished_signal = Signal(list)
        log_signal = Signal(str)
        progress_signal = Signal(int)
        total_files_signal = Signal(int)

        def __init__(self, root: Path, force=False):
            super().__init__()

            converter = ConvertXnaProjects(get_app_dir(), None, None)
            converter.log_signal.connect(self.log_signal)
            converter.progress_signal.connect(self.progress_signal)
            converter.total_files_signal.connect(self.total_files_signal)

            self.root = root
            self.converter = converter
            self.force = force

            # Forward converter signals
            # self.converter.log_signal.connect(self.log_signal)
            # self.converter.progress_signal.connect(self.progress_signal)

        @Slot()
        def run(self):

            try:
                self.log_signal.emit("Checking game cache...")

                games: list[XBLIGGame] = []
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
                        games = self.converter.find_packages(self.root)
                        save_cache(games)
                        self.log_signal.emit("Cache updated.")
                self.finished_signal.emit(games)

            except Exception as e:
                self.log_signal.emit(f"Scanner error: {e}")
                self.finished_signal.emit([])

    def rescan_games_responsive(self, force=False):
        root = Path("D:/downloads/XBLIG")

        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.scan_btn.setEnabled(False)

        self.scan_thread = QThread(self)
        self.scan_worker = self.ScanWorker(root, force)
        self.scan_worker.total_files_signal.connect(
            lambda total: (
                self.progress_bar.setRange(0, total),
                self.progress_bar.setFormat("Scanned %v files...")
            )
        )
        self.scan_worker.moveToThread(self.scan_thread)

        self.scan_thread.started.connect(self.scan_worker.run)

        self.scan_worker.log_signal.connect(self.log_message_log)
        self.scan_worker.progress_signal.connect(self.progress_bar.setValue)
        self.scan_worker.finished_signal.connect(self.scan_finished)

        # Shut the worker/thread down when scanning finishes
        self.scan_worker.finished_signal.connect(self.scan_thread.quit)
        self.scan_worker.finished_signal.connect(self.scan_worker.deleteLater)
        self.scan_thread.finished.connect(self.scan_thread.deleteLater)

        self.scan_thread.start()

    def scan_finished(self, games):
        self.games = games
        self.load_games(self.games)
        self.scan_btn.setEnabled(True)

    def log_message_log(self, message):
        logging.info(f"{message}")
        self.log_message(message)

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

        self.update_labels(game)
        # if not self.drawer_open:
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

        if game.exe:
            relative_path = game.exe.relative_to(root.parent)
            if relative_paths: self.exe_lbl.setText(str(relative_path))
            else: self.exe_lbl.setText(str(game.exe))
        else:
            self.exe_lbl.setText("-")

        if game.xml:
            relative_path = game.xml.relative_to(root.parent)
            if relative_paths: self.xml_lbl.setText(str(relative_path))
            else: self.xml_lbl.setText(str(game.xml))
        else:
            self.xml_lbl.setText("-")

        if game.extracted is not None:
            content_dir = game.extracted / "584E07D1" / "Content"
            output_dir = content_dir.parent / "Content_Output"
            if relative_paths:
                self.input_folder.setText(str(content_dir.relative_to(root.parent)))
                self.output_folder.setText(str(output_dir.relative_to(root.parent)))
            else:
                self.input_folder.setText(str(content_dir))
                self.output_folder.setText(str(output_dir))
        else:
            self.input_folder.setText(str("-"))
            self.output_folder.setText(str("-"))



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
        self.load_games(self.games)

    def extract_game(self, game=None):
        if game is None:
            if (result := self.get_selected_game()) is None:
                return
            game, _ = result

        if game.extracted is not None:
            self.log_message(f"{game.title} Already Extracted.")
            return

        if not game.package:
            self.log_message(f"{game.title} has no package.")
            return

        try:
            extracted = self.extract_package(game)

            if extracted is None:
                self.log_message(f"Failed to extract {game.title}")
                return

            game.extracted = extracted
            game.exe = next(extracted.rglob("*.exe"), None)

            self.log_message(f"Extracted {game.title} successfully")
            save_cache(self.games)

        except Exception as e:
            self.log_message(
                f"Error extracting {game.title}: {type(e).__name__}: {e}"
            )

    def extract_missing(self):
        if self.all_checkbox.isChecked():
            games = self.games
        else:
            if (result := self.get_selected_game()) is None:
                return
            game, _ = result
            games = [game]

        self.log_message(f"\nChecking {len(games)} Xbox Live Indie Games\n")

        total = len(games)

        for i, game in enumerate(games, 1):
            if game.extracted is not None or not game.package:
                self.log_message_log("Game Already Extracted")
                continue

            self.log_message(f"[{i}/{total}] Extracting {game.title}...")
            self.extract_game(game)

        self.load_games(self.games)

    def log_message(self, message):
        self.log_window.appendPlainText(message)

    def extract_package(self, game: XBLIGGame):
        package = game.package

        if not package:
            return None

        package = Path(package)

        if not package.exists():
            self.log_message_log(f"Package missing: {package}")
            return None

        from stfs_extract import extract_live_pirs

        attrs = {
            "decompiled": (
                "decompiled",
                Path("D:/downloads") / "decompiled" / game.title
            ),
            "extracted": (
                "extracted",
                Path("D:/downloads") / "extracted" / game.title
            ),
        }

        attr_name, decompiled = attrs["decompiled"]
        attr_name, extracted_path = attrs["extracted"]

        # extracted_path = package.parent / "extracted"

        extracted_path.mkdir(parents=True, exist_ok=True)

        try:
            from contextlib import redirect_stdout
            from functools import partial
            func = partial(extract_live_pirs, package, extracted_path,None)
            self.run_worker(func)
            self.log_message_log(f"Extracted to: {extracted_path}")

        except Exception as e:
            self.log_message(f"Extraction failed for {game.title}: {type(e).__name__}: {e}")
            self.log_message(traceback.format_exc())
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
                "DLL Files",
                "Content Converted",
                "Content Format"
            ]

            d = game.decompiled.name if game.decompiled else ""

            self.game_table.setItem(row, 0, QTableWidgetItem(game.title))
            self.game_table.setItem(row, 1, QTableWidgetItem(status))
            self.game_table.setItem(row, 2, QTableWidgetItem("Yes" if game.extracted else "No"))
            self.game_table.setItem(row, 4, QTableWidgetItem(game.exe.name if game.exe else ""))
            self.game_table.setItem(row, 5, QTableWidgetItem(str(len(game.dll_files)) if game.dll_files else ""))
            self.game_table.setItem(row, 3, QTableWidgetItem(d))
            self.game_table.setItem(row, 6, QTableWidgetItem(game.content_converted))
            self.game_table.setItem(row, 7, QTableWidgetItem(game.content_format))

    from PySide6.QtWidgets import (
        QDialog,
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

            self.solution_file = QLineEdit()
            self.solution_file.setText(str(r"C:\source\Indie-Games\Indie-Games.slnx"))
            self.solution_file.setMinimumHeight(28)
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
            self.convert_content_check = QCheckBox("Add To Solution")
            # self.open_vs_check = QCheckBox("Open project in Visual Studio")
            # self.open_explorer_check = QCheckBox("Open project folder in Explorer")

            self.convert_csproj_check.setChecked(True)
            self.convert_content_check.setChecked(True)

            self.decompile_check.toggled.connect(self.decompile_cli.setEnabled)
            self.decompile_check.toggled.connect(self.decompile_gui.setEnabled)

            self.decompile_cli.setEnabled(True)
            self.decompile_gui.setEnabled(True)

            options_layout.addWidget(self.solution_file)
            options_layout.addWidget(self.convert_csproj_check)
            options_layout.addWidget(self.convert_content_check)
            # options_layout.addWidget(self.open_vs_check)
            # options_layout.addWidget(self.open_explorer_check)

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
                # "open_visual_studio": self.open_vs_check.isChecked(),
                # "open_explorer": self.open_explorer_check.isChecked(),
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
            project_dir = self.decompile_selected(game, open_explorer=True, use_gui=options["decompile_gui"])
            if game.decompiled is None:
                game.decompiled = project_dir
            content_root_dir = game.extracted / "584E07D1"
            game_dll_files = game.dll_files
            copy_extracted_folder_content_and_references(source_content_root_folder=content_root_dir,
                                                         dest_content_folder=game.decompiled,
                                                         dll_files=game_dll_files,
                                                         log_callback=self.log_message)

        # if options["convert_content"]:
        #
        if options["convert_csproj"]:
            if game.decompiled is not None:
                converter = self.method_name()
                path_to_csproj_file = get_cs_project_folders([game])
                for project in path_to_csproj_file:
                    try:
                        converter.convert_project_folder(project, options["add_to_solution"])
                    except Exception as e:
                        self.log_message(f"FAILED {project}: {e}")
        if options["open_visual_studio"]:
            if game.exe is not None:
                solution = str(str(f"{str(game.exe)}.sln"))
                subprocess.Popen(["explorer", str(solution)])
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

    def open_selected_folder(self):
        if (result := self.get_selected_game()) is None:
            return
        game, indexes = result
        if not game or not game.game_root or not game.game_root.exists():
            self.log_message("No valid game folder selected.")
            return

        subprocess.Popen(["explorer", str(game.game_root)])
        self.log_message(f"Opened: {game.game_root}")

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

        self.title_lbl = QLabel("-")
        self.titleid_lbl = QLabel("-")
        self.dll_files_lbl = QLabel("-")
        self.exe_lbl = QLabel("-")
        self.xml_lbl = QLabel("-")
        self.status_lbl = QLabel("-")

        form.addRow("Title", self.title_lbl)
        form.addRow("Title ID", self.titleid_lbl)
        form.addRow("DLL Files", self.dll_files_lbl)
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

    def build_ui(self):

        main_layout = QVBoxLayout(self)

        #
        # Toolbar
        #

        toolbar = QHBoxLayout()
        self.scan_btn = QPushButton("Scan Games")
        self.scan_btn.clicked.connect(self.rescan_games_responsive)
        self.scan_btn.setFixedWidth(120)

        self.extract_btn = QPushButton("Extract Selected Game Package")
        self.extract_btn.clicked.connect(self.extract_missing)
        self.extract_btn.setFixedWidth(240)

        self.build_btn = QPushButton("Decompile Game")
        self.build_btn.clicked.connect(self.build_selected)
        self.build_btn.setFixedWidth(240)
        # self.random_btn = QPushButton("Random Game")
        # self.random_btn.clicked.connect(self.build_selected)

        # self.build_content_btn = QPushButton("Convert Content")
        # self.build_content_btn.clicked.connect(self.convert_content)
        #
        # self.convert_one_btn = QPushButton("Convert (Selected) Game to FNA Project")
        # self.convert_one_btn.clicked.connect(self.convert_selected_folders)

        self.convert_project_btn = QPushButton("Convert Game Project")
        self.convert_project_btn.clicked.connect(self.convert_game_project)
        self.convert_project_btn.setFixedWidth(240)
        #
        # self.launch_btn = QPushButton("Launch Game")
        # self.launch_btn.clicked.connect(self.launch_selected)
        #
        # self.refresh_btn = QPushButton("Refresh")
        # self.refresh_btn.clicked.connect(self.refresh_games)
        # #
        self.open_folder_btn = QPushButton("Open Folder")
        self.open_folder_btn.clicked.connect(self.open_selected_folder)

        self.compress_btn = QPushButton("Compress Selected Extracted Content")
        self.compress_btn.clicked.connect(partial(self.compress_decompress_extracted_content, True))
        # self.compress_btn.setFixedWidth(320)

        self.decompress_btn = QPushButton("Decompress Selected Extracted Content")
        self.decompress_btn.clicked.connect(partial(self.compress_decompress_extracted_content, False))
        # self.decompress_btn.setFixedWidth(320)

        self.all_checkbox = QCheckBox("All or One")
        self.all_checkbox.toggled.connect(self.all_or_one)

        toolbar.addWidget(self.scan_btn)
        toolbar.addWidget(self.build_btn)
        toolbar.addWidget(self.extract_btn)

        toolbar.addWidget(self.convert_project_btn)
        # toolbar.addWidget(self.launch_btn)
        toolbar.addWidget(self.open_folder_btn)
        # toolbar.addWidget(self.refresh_btn)
        toolbar.addWidget(self.compress_btn)
        toolbar.addWidget(self.decompress_btn)
        toolbar.addWidget(self.all_checkbox)
        toolbar.addStretch()

        # for button in (self.scan_btn, self.extract_btn, self.build_btn, self.convert_project_btn, self.compress_btn):
        #     button.setFixedSize(200, 32)

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

        self.game_table = QTableWidget(0, 8)

        columns = [
            "Title",
            "Status",
            "Extracted",
            "Decompiled",
            "Executable",
            "DLL Files",
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

        self.game_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.game_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.game_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        self.game_table.itemSelectionChanged.connect(self.game_selected)

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

        self.game_table.selectRow(0)

    def add_demo_game(self, title, status, extracted, exe):

        row = self.game_table.rowCount()

        self.game_table.insertRow(row)

        self.game_table.setItem(row, 0, QTableWidgetItem(title))
        self.game_table.setItem(row, 1, QTableWidgetItem(status))
        self.game_table.setItem(row, 2, QTableWidgetItem(extracted))
        self.game_table.setItem(row, 3, QTableWidgetItem(exe))

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
