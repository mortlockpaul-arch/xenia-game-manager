import os
import string
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QThread, Signal

from config import get_app_dir

ROM_FOLDER_NAMES = {"rom", "roms"}
XBOX_FOLDER_NAMES = {"xbox", "xbox roms", "xbox games", "original xbox", "original xbox games"}
SKIP_FOLDER_NAMES = {"$recycle.bin", "system volume information", "windows", "program files", "program files (x86)", "programdata", "appdata"}

@dataclass(frozen=True, slots=True)
class XboxRom:
    file: Path
    rom_path: Path

class XboxScanner(QThread):
    finished_scan = Signal(list)
    status = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stop_requested = False

    def stop(self):
        self._stop_requested = True

    def run(self):
        xbox_game_list: list[XboxRom] = []
        found_files = set()

        self.status.emit("Looking for Xbox ROM folders...")
        xbox_folders = self._find_xbox_folders()

        if self._stop_requested:
            self.finished_scan.emit(xbox_game_list)
            return

        self.status.emit(f"Found {len(xbox_folders)} Xbox ROM folders")

        # for xbox_folder in xbox_folders:
        # if self._stop_requested:
        #     break
        self._scan_xisos(xbox_folders, xbox_game_list, found_files)

        xbox_game_list.sort(key=lambda x: str(x.file).lower())
        self.status.emit(f"Xbox XISO scan complete — {len(xbox_game_list)} files found")
        self.finished_scan.emit(xbox_game_list)

    def _find_xbox_folders(self):
        xbox_folders: list[Path] = []
        found_folders = set()

        for drive_letter in string.ascii_uppercase:
            if self._stop_requested:
                break

            drive = Path(f"{drive_letter}:\\")
            if not drive.exists():
                continue

            rom_folders = self._find_direct_children(drive, ROM_FOLDER_NAMES)

            for rom_folder in rom_folders:
                if self._stop_requested:
                    break

                xbox_dirs = self._find_direct_children(rom_folder, XBOX_FOLDER_NAMES)

                for xbox_dir in xbox_dirs:
                    try:
                        xbox_dir = xbox_dir.resolve()
                    except OSError:
                        continue

                    if xbox_dir in found_folders:
                        continue

                    found_folders.add(xbox_dir)
                    xbox_folders.append(xbox_dir)

        return xbox_folders

    def _find_direct_children(self, root, wanted_names):
        found: list[Path] = []

        try:
            with os.scandir(root) as entries:
                for entry in entries:
                    if self._stop_requested:
                        return found

                    try:
                        if not entry.is_dir(follow_symlinks=False):
                            continue

                        if entry.name.lower() in SKIP_FOLDER_NAMES:
                            continue

                        if entry.name.lower() in wanted_names:
                            found.append(Path(entry.path))

                    except (PermissionError, OSError):
                        continue

        except (PermissionError, OSError):
            pass

        return found

    def _scan_xisos(self, directories: list[Path], xboxrom_list, found_files):
        # directories: list[Path] = directories

        while directories:
            if self._stop_requested:
                return

            current = directories.pop()
            self.status.emit(f"Scanning: {current}")
            try:
                with os.scandir(current) as entries:
                    for entry in entries:
                        if self._stop_requested:
                            return

                        try:
                            if entry.is_file(follow_symlinks=False):
                                name = entry.name.lower()

                                if not (name.endswith(".xiso") or name.endswith(".xiso.iso")):
                                    continue

                                path = Path(entry.path)

                                try:
                                    path = path.resolve()
                                except OSError:
                                    continue

                                if path in found_files:
                                    continue
                                self.status.emit(f"Found Xbox Game {path}")
                                found_files.add(path)
                                xboxrom_list.append(XboxRom(file=path, rom_path=path))
                                continue

                            if entry.is_dir(follow_symlinks=False):
                                if entry.name.lower() in SKIP_FOLDER_NAMES:
                                    continue

                                directories.append(Path(entry.path))

                        except (PermissionError, OSError):
                            continue

            except (PermissionError, OSError):
                continue

from pathlib import Path
import json
import shutil
import subprocess
import requests


XDB_URL = "https://github.com/xemu-project/xdb.git"
REPORTS_URL = "https://reports.xemu.app/compatibility"

from dataclasses import dataclass, field
from pathlib import Path
import json

@dataclass
class XemuCompatibilityGame:
    title_id: str
    name: str
    status: str
    status_description: str
    url: str
    images: dict[str, str] = field(default_factory=dict)
    report: dict | None = None
    last_tested: str | None = None

    @property
    def last_tested_text(self) -> str:
        return self.last_tested or "Never"


@dataclass
class XemuCompatibility:
    source: str
    xdb: str
    reports: str
    games: dict[str, XemuCompatibilityGame] = field(
        default_factory=dict
    )


def load_xemu_compatibility(output_dir= get_app_dir() / "compatibility/xemu_compatibility",) -> XemuCompatibility:
    output = Path(output_dir)
    json_file = output / "xemu_compatibility.json"

    if not json_file.exists():
        raise FileNotFoundError(json_file)

    data = json.loads(
        json_file.read_text(encoding="utf-8")
    )

    games = {}

    for title_id, game_data in data.get("games", {}).items():
        game = XemuCompatibilityGame(
            title_id=game_data["title_id"],
            name=game_data.get("name", ""),
            status=game_data.get("status", "Unknown"),
            status_description=game_data.get(
                "status_description",
                "",
            ),
            url=game_data.get("url", ""),
            images=game_data.get("images", {}),
            report=game_data.get("report"),
            last_tested=game_data.get("last_tested"),
        )

        games[title_id.upper()] = game

    return XemuCompatibility(
        source=data.get("source", ""),
        xdb=data.get("xdb", ""),
        reports=data.get("reports", ""),
        games=games,
    )

def get_artwork_icon_path(title_id=None):
    image_dir = Path("compatibility/xemu_compatibility") / "images" / title_id / "xtimage.png"
    return image_dir

def update_xemu_compatibility(output_dir="compatibility/xemu_compatibility"):
    output = Path(output_dir)
    xdb = output / "xdb"
    images = output / "images"
    json_file = output / "xemu_compatibility.json"

    output.mkdir(parents=True, exist_ok=True)

    # Clone once, pull thereafter.
    if xdb.exists():
        subprocess.run(
            ["git", "-C", str(xdb), "pull", "--ff-only"],
            check=True,
            capture_output=True,
            text=True
        )
    else:
        subprocess.run(
            ["git", "clone", "--depth", "1", XDB_URL, str(xdb)],
            check=True,
            capture_output=True,
            text=True
        )

    # Download current compatibility reports.
    reports = requests.get(REPORTS_URL, timeout=60)
    reports.raise_for_status()
    reports = reports.json()

    # Index reports by Title ID and keep the newest report.
    latest = {}

    for report in reports:
        title_id = f"{report['xbe_cert_title_id']:08X}"
        current = latest.get(title_id)

        if current is None or report["created_at"] > current["created_at"]:
            latest[title_id] = report

    games = {}

    # Read XDB title metadata.
    for info_file in xdb.glob("titles/*/*/info.json"):
        info = json.loads(info_file.read_text(encoding="utf-8"))

        title_id = info["title_id"].upper()
        title_dir = info_file.parent
        report = latest.get(title_id)

        status = report["compat_rating"] if report else "Unknown"

        game = {
            "title_id": title_id,
            "name": info.get("name", ""),
            "status": status,
            "status_description": {
                "Unknown": "A compatibility test has not been recorded for this title.",
                "Broken": "This title crashes very soon after launching, or displays nothing at all.",
                "Intro": "This title displays an intro sequence, but fails to make it to gameplay.",
                "Starts": "This title starts, but may crash or have significant issues.",
                "Playable": "This title is playable, with minor issues.",
                "Perfect": "This title is playable from start to finish with no noticeable issues."
            }.get(status, ""),
            "url": f"https://xemu.app/titles/{title_id.lower()}",
            "images": {}
        }

        if report:
            game["report"] = report
            game["last_tested"] = report.get("created_at")

        # Copy artwork into a simple Title-ID based directory.
        image_dir = images / title_id
        image_dir.mkdir(parents=True, exist_ok=True)

        for source_name, output_name in (
            ("cover_front.jpg", "front.jpg"),
            ("cover_front.png", "front.png"),
            ("cover_back.jpg", "back.jpg"),
            ("cover_back.png", "back.png"),
            ("media.jpg", "disc.jpg"),
            ("media.png", "disc.png"),
            ("xtimage.png", "xtimage.png"),
        ):
            source = title_dir / source_name

            if source.exists():
                destination = image_dir / output_name

                if not destination.exists() or source.stat().st_mtime > destination.stat().st_mtime:
                    shutil.copy2(source, destination)

                game["images"][output_name.rsplit(".", 1)[0]] = str(
                    destination.relative_to(output)
                )

        games[title_id] = game

    json_file.write_text(
        json.dumps(
            {
                "source": "https://xemu.app/#compatibility",
                "xdb": "https://github.com/xemu-project/xdb",
                "reports": REPORTS_URL,
                "games": games
            },
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    return load_xemu_compatibility(output)


def load_compatibility_test():
    compatibility = load_xemu_compatibility()
    game = compatibility.games.get("584109E4")

    if game:
        print(game.name)
        print(game.status)
        print(game.last_tested_text)
        print(game.images)

    for game in compatibility.games.values():
        print(
            game.title_id,
            game.name,
            game.status,
        )

def update_compatibility_test():
    compatibility_update = update_xemu_compatibility()
    game = compatibility_update.games.get("584109E4")

    if game:
        print(game.name)
        print(game.status)
        print(game.last_tested_text)
        print(game.images)

# method_name()

if __name__ == "__main__":
    load_compatibility_test()
