from __future__ import annotations
import json
import shutil
import sqlite3
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Literal
from pathlib import Path
import requests
from config import load_config_file, get_app_dir
from edge_import import import_edge_games, XeniaEdgeGame
from logging_setup import logger
from utils import detect_disc_number, strip_disc_suffix, smart_title_case
from xiso import XboxRom, load_xemu_compatibility, XemuCompatibility, XemuCompatibilityGame
from enum import Enum
from pathlib import Path
from dataclasses import fields

DB_PATH = Path(__file__).resolve().parent / "database" / "games.db"

from dataclasses import dataclass, field, fields


class Platform(Enum):
    XBOX = "Xbox"
    XBOX360 = "Xbox360"
    INDIE = "Indie"

    @property
    def display_name(self):
        return {
            Platform.XBOX: "Xbox",
            Platform.XBOX360: "Xbox 360",
            Platform.INDIE: "Indie"
        }[self]


def _json_value(value):
    if isinstance(value, Path):
        return str(value)

    if isinstance(value, Enum):
        return value.value

    if isinstance(value, list):
        return [_json_value(item) for item in value]

    if isinstance(value, dict):
        return {
            key: _json_value(item)
            for key, item in value.items()
        }

    return value


@dataclass
class ConversionResult:
    tool: str
    success: bool
    input_file: Path
    output_files: list[Path]
    stdout: str
    stderr: str
    error: str | None = None


@dataclass
class Game:
    game_id: str
    title: str
    platform: Platform
    favourite: bool = False
    last_played: str | None = None
    play_count: int = 0
    play_time: int = 0


@dataclass
class XBLIGGame(Game):
    platform: Platform = field(default=Platform.INDIE, init=False, )

    title: str = ""
    icon: Path | None = None

    folder_title: str | None = None
    title_id: str | None = None
    virtual_title_id: str | None = None
    xml_title_id: str | None = None
    publisher: str | None = None

    content_type: str | None = None
    content_name: str | None = None
    content_converted: str = "No"
    content_format: str = "xnb content"

    package: Path | None = None
    extracted: Path | None = None
    game_root: Path | None = None

    executables: list[Path] = field(default_factory=list)
    dll_files: list[Path] = field(default_factory=list)
    xml: Path | None = None
    decompiled: Path | None = None

    def __post_init__(self):
        for name in (
                "package",
                "extracted",
                "game_root",
                "xml",
                "decompiled",
                "icon",
        ):
            value = getattr(self, name)
            if isinstance(value, str):
                setattr(self, name, Path(value))

    @classmethod
    def from_dict(cls, data: dict) -> "XBLIGGame":
        path_fields = {
            "package",
            "extracted",
            "game_root",
            "xml",
            "decompiled",
            "icon",
        }

        list_path_fields = {
            "executables",
            "dll_files",
        }

        values = {}

        valid_fields = {
            field_info.name
            for field_info in fields(cls)
            if field_info.init
        }

        for key, value in data.items():
            if key not in valid_fields:
                continue

            if key in path_fields:
                if value:
                    value = Path(value)

            elif key in list_path_fields:
                value = [
                    Path(item) if item else item
                    for item in (value or [])
                ]

            values[key] = value

        return cls(**values)

    def to_dict(self):
        return {
            field_info.name: _json_value(
                getattr(self, field_info.name)
            )
            for field_info in fields(self)
            if field_info.init
        }


@dataclass
class GameDisc:
    media_id: str | None = None
    file_path: Path | None = None
    disc_count: int = 1
    disc_type: str | None = None
    disc_swap_required: bool = False
    disc_number: int = 1
    label: str | None = None

    @classmethod
    def from_row(cls, row) -> "GameDisc":
        return cls(
            media_id=row["media_id"],
            file_path=(
                Path(row["file_path"])
                if row["file_path"]
                else None
            ),
            disc_count=row["disc_count"] or 1,
            disc_type=row["disc_type"],
            disc_swap_required=bool(
                row["disc_swap_required"]
            ),
            disc_number=row["disc_number"] or 1,
            label=row["label"],
        )


@dataclass
class Xbox360Game(Game):
    platform: Platform = field(default=Platform.XBOX360, init=False)
    emulator: str = field(default="xenia", init=False)
    config_path: Path | None = None
    discs: list[GameDisc] = field(default_factory=list)

    @classmethod
    def from_row(cls, row):
        discs = []

        if row["disc_number"] is not None:
            discs.append(GameDisc.from_row(row))

        return cls(
            game_id=row["game_id"],
            title=row["title"],
            config_path=(
                Path(row["config_path"])
                if row["config_path"]
                else None
            ),
            favourite=bool(row["favourite"]),
            last_played=row["last_played"],
            play_count=row["play_count"] or 0,
            play_time=row["play_time"] or 0,
            discs=discs,
        )


@dataclass
class XboxGame(Game):
    platform: Platform = field(default=Platform.XBOX, init=False, )
    emulator: str = field(default="xemu", init=False, )
    config_path: Path | None = None

    @classmethod
    def from_row(cls, row):
        discs = []

        if row["disc_number"] is not None:
            discs.append(GameDisc.from_row(row))

        return cls(
            game_id=row["game_id"],
            title=row["title"],
            config_path=(
                Path(row["config_path"])
                if row["config_path"]
                else None
            ),
            favourite=bool(row["favourite"]),
            last_played=row["last_played"],
            play_count=row["play_count"] or 0,
            play_time=row["play_time"] or 0,
        )

    @classmethod
    def from_dict(cls, data: dict) -> "XboxGame":
        config_path:str = data.get("config_path")

        discs = [
            GameDisc(
                media_id=disc.get("media_id"),
                file_path=(
                    Path(disc["file_path"])
                    if disc.get("file_path")
                    else None
                ),
                disc_count=disc.get("disc_count", 1),
                disc_type=disc.get("disc_type"),
                disc_swap_required=bool(
                    disc.get("disc_swap_required", False)
                ),
                disc_number=disc.get("disc_number", 1),
                label=disc.get("label"),
            )
            for disc in data.get("discs", [])
        ]

        return cls(
            game_id=data["game_id"],
            title=data.get("title", ""),
            config_path=(
                Path(config_path)
                if config_path
                else None
            ),
            favourite=bool(data.get("favourite", False)),
            last_played=data.get("last_played"),
            play_count=data.get("play_count", 0),
            play_time=data.get("play_time", 0),
        )


class Compatibility:

    def __init__(self, db, log_call_back=None):
        self.compatibility = None
        root = get_app_dir()
        self.compatibility_file = root / "config" / "xenia_compatibility.json"

        needs_download = (
                not self.compatibility_file.exists()
                or datetime.now() - datetime.fromtimestamp(self.compatibility_file.stat().st_mtime) >= timedelta(days=1)
        )

        if needs_download:
            if self.compatibility_file.exists():
                (log_call_back or print)(
                    f"File {self.compatibility_file} is over 1 day old. Downloading compatibility data."
                )
            else:
                (log_call_back or print)(
                    f"File {self.compatibility_file} does not exist. Downloading compatibility data."
                )

            self.download_xenia_compatibility()
        else:
            modified = datetime.fromtimestamp(self.compatibility_file.stat().st_mtime)
            (log_call_back or print)(
                f"Compatibility data is up to date "
                f"(last updated {modified:%Y-%m-%d %H:%M:%S})."
            )

        self.db = db

    def download_xenia_compatibility(self):
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "XeniaGameManager"
        }
        config = load_config_file()
        api = config["xenia_game_compatibility_url"]
        release = requests.get(api, headers=headers, timeout=30)
        release.raise_for_status()

        release = release.json()

        print(release["tag_name"])

        for asset in release["assets"]:
            print(asset["name"], asset["browser_download_url"])

        asset = next(
            a for a in release["assets"]
            if a["name"].endswith(".json")
        )

        download_url = asset["browser_download_url"]

        response = requests.get(download_url, headers=headers, timeout=60)
        response.raise_for_status()

        self.compatibility = response.json()

        with open(self.compatibility_file, "wb") as f:
            f.write(response.content)

    def update_compatibility(self):
        if self.compatibility is None:
            with open(self.compatibility_file, "r", encoding="utf-8") as f:
                self.compatibility = json.load(f)

        compat_by_title: dict[str, dict[str, Any]] = {
            game["id"].upper(): game
            for game in self.compatibility
        }

        with self.db.get_db() as con:
            rows = con.execute(
                "SELECT game_id FROM games"
            ).fetchall()

            for row in rows:
                game_id = row["game_id"].upper()
                compat = compat_by_title.get(game_id)

                if compat:
                    con.execute("""
                        INSERT INTO compatibility (
                            game_id,
                            compatibility_rating,
                            compatibility_issue,
                            compatibility_updated
                        )
                        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                        ON CONFLICT(game_id)
                        DO UPDATE SET
                            compatibility_rating = excluded.compatibility_rating,
                            compatibility_issue = excluded.compatibility_issue,
                            compatibility_updated = CURRENT_TIMESTAMP
                    """, (
                        row["game_id"],
                        compat["state"],
                        compat.get("issue", ""),
                    ))


class Emulator(Enum):
    XEMU = "xemu"
    XENIA = "xenia"


def create_xbox360_game_from_xenia_manager(data, ) -> Xbox360Game:
    game_id = data.get("game_id")

    file_path = data.get(
        "file_locations", {}
    ).get("game")

    config_path = data.get(
        "file_locations", {}
    ).get("config")

    additional_discs = data.get("file_locations", {}).get("additional_discs", {})

    disc = GameDisc(
        media_id=data.get("media_id"),
        file_path=Path(file_path) if file_path else None,
        disc_number=detect_disc_number(file_path),
        disc_type=(
            "XBLA"
            if game_id
               and file_path
               and game_id.lower() in file_path.lower()
            else "DVD"
        ),
    )

    return Xbox360Game(
        game_id=game_id,
        title=strip_disc_suffix(data.get("title") or ""),
        config_path=Path(config_path) if config_path else None,
        play_time=data.get("playtime") or 0,
        emulator_version=data.get("xenia_version"),
        discs=[disc],
    )


def create_xbox360_game_from_edge(
        data: XeniaEdgeGame,
) -> Xbox360Game:
    disc = GameDisc(
        file_path=data.path,
        disc_type="DVD",
    )

    return Xbox360Game(
        game_id=data.title_id,
        title=strip_disc_suffix(data.name),
        discs=[disc],
    )


#
# "games": {
#   "41430001": {
#     "title_id": "41430001",
#     "name": "Dave Mirra Freestyle BMX 2",
#     "status": "Playable",
#     "status_description": "This title is playable, with minor issues.",
#     "url": "https://xemu.app/titles/41430001",
#     "images": {
#       "front": "images\\41430001\\front.jpg",
#       "back": "images\\41430001\\back.jpg",
#       "disc": "images\\41430001\\disc.jpg",
#       "xtimage": "images\\41430001\\xtimage.png"
#     },
#     "report": {
#       "created_at": 1656748603,
#       "xbe_cert_title_id": 1094909953,
#       "xbe_headers_sha256": "6c17491189e515042ee99d05d1c84a589a0209f8f58a76a85a8d2fdd91775e3b",
#       "xemu_version": "0.7.56",

def find_xemu_compatibility_by_name(
        compatibility: XemuCompatibility,
        name: str,
) -> XemuCompatibilityGame | None:
    name = name.strip().casefold()

    return next(
        (
            game
            for game in compatibility.games.values()
            if game.name.strip().casefold() == name
        ),
        None,
    )


def clean_xbox_title(filename: str | Path, normalise_separators=False) -> str:
    title = Path(filename).name

    # Remove .iso / .xiso / .xiso.iso etc.
    while Path(title).suffix.lower() in {".iso", ".xiso"}:
        title = Path(title).stem

    # Remove region/language/revision information
    title = title.split("(", 1)[0]

    if normalise_separators:
        title = title.replace("_", " ").replace("-", " ")

    return " ".join(title.split()).strip()


def create_xbox_game(data: XboxRom, compatibility=None) -> XboxGame:
    global game_id, xemu_version

    file = data.file
    file_path = data.rom_path
    title = clean_xbox_title(data.file.stem)
    compat_game = find_xemu_compatibility_by_name(
        compatibility,
        title,
    )
    if compat_game:
        title = compat_game.name
        status = compat_game.status
        status_description = compat_game.status_description
        images = compat_game.images
        last_tested = compat_game.last_tested
        game_id = compat_game.title_id
        media_id = "41430001"
        xemu_version = compat_game.report.get("xemu_version", None) if compat_game.report else None
    else:
        title = data.file.stem
        status = "Unknown"
        status_description = ""
        images = {}
        last_tested = None

    disc = GameDisc(
        media_id=game_id,
        file_path=Path(file) if file else None,
        disc_number=detect_disc_number(title),
        disc_type="DVD",
    )

    return XboxGame(
        game_id=game_id,
        title=strip_disc_suffix(title or ""),
        config_path=Path("D:/RetroBat/emulators/xemu/xemu.toml"),
        play_time=0,
        emulator_version=xemu_version,
        discs=[disc],
    )


def xenia_edge_game_from_dict(data) -> Xbox360Game:
    game_id = data.get("title_id")
    file_path = data.get("path")

    disc_number = detect_disc_number(file_path)

    disc_type = (
        "XBLA"
        if game_id
           and file_path
           and game_id.lower() in file_path.lower()
        else "DVD"
    )

    disc = GameDisc(
        file_path=Path(file_path) if file_path else None,
        disc_number=disc_number,
        disc_type=disc_type,
    )

    edge_path = Path(
        load_config_file()["xenia_edge_path"]
    )

    edge_configs = (
            Path.home()
            / "Documents"
            / "Xenia"
            / "config"
    )

    if (edge_path / "portable.txt").exists():
        edge_configs = edge_path / "content"

    config_path = edge_configs / f"{game_id}.config.toml"

    return Xbox360Game(
        game_id=game_id,
        title=data.get("name") or "",
        config_path=config_path,
        emulator_version="Edge",
        discs=[disc],
    )


def xenia_manager_game_from_dict(data) -> Xbox360Game:
    game_id = data.get("game_id")

    file_path = (
        data.get("file_locations", {})
        .get("game")
    )

    config_path = (
        data.get("file_locations", {})
        .get("config")
    )

    disc_number = detect_disc_number(file_path)

    disc_type = (
        "XBLA"
        if game_id
           and file_path
           and game_id.lower() in file_path.lower()
        else "DVD"
    )

    disc = GameDisc(
        media_id=data.get("media_id"),
        file_path=Path(file_path) if file_path else None,
        disc_number=disc_number,
        disc_type=disc_type,
    )

    return Xbox360Game(
        game_id=game_id,
        title=strip_disc_suffix(data.get("title") or ""),
        config_path=Path(config_path) if config_path else None,
        play_time=data.get("playtime") or 0,
        emulator_version=data.get("xenia_version"),
        discs=[disc],
    )


def xemu_game_from_dict(data) -> XboxGame:
    game_id = data.get("game_id")

    file_path = (
        data.get("file_locations", {})
        .get("game")
    )

    config_path = (
        data.get("file_locations", {})
        .get("config")
    )

    disc_number = detect_disc_number(file_path)

    disc_type = (
        "XBLA"
        if game_id
           and file_path
           and game_id.lower() in file_path.lower()
        else "DVD"
    )

    disc = GameDisc(
        media_id=data.get("media_id"),
        file_path=Path(file_path) if file_path else None,
        disc_number=disc_number,
        disc_type=disc_type,
    )

    return XboxGame(
        game_id=game_id,
        title=strip_disc_suffix(data.get("title") or ""),
        config_path=Path(config_path) if config_path else None,
        play_time=data.get("playtime") or 0,
    )


GameSource = Literal["xemu", "xenia_manager", "xenia_edge", "indie"]


class Database:

    def __init__(self):
        self.compatibility = None
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
        self.conn.execute("PRAGMA foreign_keys = ON")

    def import_multidisc_json(self, json_path, log_callback=None):
        """Import multi-disc preservation metadata."""

        with open(json_path, "r", encoding="utf-8") as f:
            entries = json.load(f)["entries"]

        imported = 0

        platform = "xbox360"

        with self.conn as con:
            for game in entries:
                game_id = game["title_id"]

                # Skip games that aren't in the library
                if not con.execute(
                        """
                        SELECT 1
                        FROM games
                        WHERE platform = ?
                          AND game_id = ?
                        """,
                        (platform, game_id),
                ).fetchone():
                    continue

                imported += 1

                con.execute(
                    """
                    UPDATE games
                    SET title = ?
                    WHERE platform = ?
                      AND game_id = ?
                    """,
                    (
                        game["title"],
                        platform,
                        game_id,
                    ),
                )

                for disc_number, label in enumerate(
                        game["disc_layout"],
                        start=1,
                ):
                    con.execute(
                        """
                        INSERT INTO discs (
                            platform,
                            game_id,
                            disc_count,
                            disc_type,
                            disc_swap_required,
                            disc_number,
                            label
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?)

                        ON CONFLICT(platform, game_id, disc_number)
                        DO UPDATE SET
                            disc_count = excluded.disc_count,
                            disc_type = excluded.disc_type,
                            disc_swap_required =
                                excluded.disc_swap_required,
                            label = excluded.label
                        """,
                        (
                            platform,
                            game_id,
                            game["disc_count"],
                            game["disc_type"],
                            int(game.get(
                                "xenia_disc_swap_required",
                                False,
                            )),
                            disc_number,
                            label,
                        ),
                    )

        if log_callback:
            log_callback(
                f"Imported multi-disc metadata for {imported} games"
            )

    def get_game_discs(self, title_id):

        with self.conn as con:
            return [
                dict(row)
                for row in con.execute("""
                    SELECT
                        disc_number,
                        label,
                        file_path
                    FROM discs
                    WHERE title_id = ?
                    ORDER BY disc_number
                """, (title_id,))
            ]

    def get_multidisc_games(self):

        with self.conn as con:
            return [
                dict(row)
                for row in con.execute("""
                    SELECT
                        game_id,
                        title,
                        disc_count,
                        disc_type
                    FROM games
                    WHERE disc_count > 1
                    ORDER BY title
                """)
            ]

    from contextlib import contextmanager

    @contextmanager
    def get_db(self):
        con = sqlite3.connect(DB_PATH)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")

        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def clear_db(self, delete_favourites=False, delete_discs=False):
        with self.conn as con:
            if delete_discs:
                con.execute("DELETE FROM discs")
                con.execute("DELETE FROM sqlite_sequence WHERE name='discs'")
            con.execute("DELETE FROM games")
            if delete_favourites: con.execute("DELETE FROM favourites")
            con.execute("DELETE FROM sqlite_sequence WHERE name='games'")
            con.commit()

    def get_xblig_metadata(self, title: str) -> dict | None:
        """Return XBLIG catalogue metadata for a game title."""
        normalized_title = " ".join(
            title.casefold().strip().split()
        )

        cursor = self.conn.execute(
            """
            SELECT
                id,
                title,
                developer,
                developer_account,
                genre,
                release_date,
                user_rating,
                rating_count,
                file_size,
                available_on,
                links,
                notes,
                updates,
                category_scores,
                timecode,
                gamefaqs,
                title_text_from_youtube
            FROM xblig_metadata
            WHERE normalized_title = ?
            LIMIT 1
            """,
            (normalized_title,),
        )

        row = cursor.fetchone()

        if row is None:
            return None

        columns = [column[0] for column in cursor.description]

        return dict(zip(columns, row))

    def init_db(self):
        with self.conn as con:
            con.execute("""
            CREATE TABLE IF NOT EXISTS games (
                game_id TEXT NOT NULL,
                platform TEXT NOT NULL,
                title TEXT NOT NULL,
                config_path TEXT,
                UNIQUE(platform, game_id),
                PRIMARY KEY(platform, game_id)
            );
            """)

            con.execute("""
            CREATE TABLE IF NOT EXISTS emulators (
                platform TEXT NOT NULL,
                emulator TEXT NOT NULL,
                version TEXT,
                PRIMARY KEY(platform, emulator)
            );
            """)

            con.execute("""
            CREATE TABLE IF NOT EXISTS compatibility (
                platform TEXT NOT NULL,
                game_id TEXT NOT NULL,
                emulator TEXT NOT NULL,
                compatibility_rating TEXT,
                compatibility_issue TEXT,
                compatibility_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(platform, game_id, emulator),
                FOREIGN KEY(platform, game_id)
                    REFERENCES games(platform, game_id)
                    ON DELETE CASCADE
            );
            """)

            con.execute("""
            CREATE TABLE IF NOT EXISTS gameplay (
                platform TEXT NOT NULL,
                game_id TEXT NOT NULL,
                last_played TEXT,
                play_count INTEGER DEFAULT 0,
                play_time INTEGER DEFAULT 0,
                PRIMARY KEY(platform, game_id),
                FOREIGN KEY(platform, game_id)
                    REFERENCES games(platform, game_id)
                    ON DELETE CASCADE
            );
            """)

            con.execute("""
            CREATE TABLE IF NOT EXISTS favourites (
                platform TEXT NOT NULL,
                game_id TEXT NOT NULL,
                favourite INTEGER DEFAULT 0,
                PRIMARY KEY(platform, game_id),
                FOREIGN KEY(platform, game_id)
                    REFERENCES games(platform, game_id)
                    ON DELETE CASCADE
            );
            """)

            con.execute("""
            CREATE TABLE IF NOT EXISTS discs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                game_id TEXT NOT NULL,
                media_id TEXT,
                file_path TEXT,
                disc_count INTEGER DEFAULT 1,
                disc_type TEXT,
                disc_swap_required INTEGER DEFAULT 0,
                disc_number INTEGER DEFAULT 1,
                label TEXT,
                UNIQUE(platform, game_id, disc_number),

                FOREIGN KEY(platform, game_id)
                    REFERENCES games(platform, game_id)
                    ON DELETE CASCADE
            );
            """)

            con.execute("""
            CREATE VIEW IF NOT EXISTS game_view AS
            SELECT
                g.platform,
                g.game_id,
                d.media_id,

                CASE
                    WHEN d.disc_count > 1
                    THEN g.title || ' - ' || d.label
                    ELSE g.title
                END AS title,

                g.config_path,

                d.file_path,
                d.disc_number,
                d.disc_count,
                d.disc_type,
                d.disc_swap_required,
                d.label,

                COALESCE(f.favourite, 0) AS favourite,

                p.last_played,
                COALESCE(p.play_count, 0) AS play_count,
                COALESCE(p.play_time, 0) AS play_time,

                c.emulator,
                e.version AS emulator_version,
                c.compatibility_rating,
                c.compatibility_issue,
                c.compatibility_updated

            FROM games g

            JOIN discs d
                ON g.platform = d.platform
                AND g.game_id = d.game_id

            LEFT JOIN gameplay p
                ON g.platform = p.platform
                AND g.game_id = p.game_id

            LEFT JOIN favourites f
                ON g.platform = f.platform
                AND g.game_id = f.game_id

            LEFT JOIN compatibility c
                ON g.platform = c.platform
                AND g.game_id = c.game_id

            LEFT JOIN emulators e
                ON c.platform = e.platform
                AND c.emulator = e.emulator;
            """)

            con.execute("""
            CREATE VIEW IF NOT EXISTS disc_view AS
            SELECT
                d.id,
                d.platform,
                d.game_id,
                g.title,
                d.disc_number,
                d.file_path,
                d.label
            FROM discs d
            JOIN games g
                ON d.platform = g.platform
                AND d.game_id = g.game_id;
            """)

            con.execute("""
            CREATE INDEX IF NOT EXISTS idx_games_title
            ON games(title);
            """)

            con.execute("""
            CREATE INDEX IF NOT EXISTS idx_games_platform
            ON games(platform);
            """)

            con.execute("""
            CREATE INDEX IF NOT EXISTS idx_discs_game
            ON discs(platform, game_id);
            """)

    def export_titles_to_xenia_manager_game_list(self):
        import json
        config = load_config_file()
        xenia_manager_installed = config["xenia_manager_installed"]
        if xenia_manager_installed:
            xenia_manager_path = config["xenia_manager_path"]
            games_json_path = Path(xenia_manager_path) / Path("config") / "games.json"
            if not games_json_path.exists():
                raise Exception("Missing File")
            with open(games_json_path, "r", encoding="utf-8") as f:
                games = json.load(f)

            with self.conn as con:

                db_titles = {
                    row["game_id"]: row["title"]
                    for row in con.execute(
                        """
                        SELECT game_id, title
                        FROM games
                        """
                    ).fetchall()
                }

            updated = 0

            for game in games:

                game_id = game.get("game_id")

                if game_id in db_titles:

                    new_title = db_titles[game_id]

                    if game.get("title") != new_title:
                        game["title"] = new_title
                        updated += 1

            with open(games_json_path, "w", encoding="utf-8") as f:
                json.dump(
                    games,
                    f,
                    indent=2,
                    ensure_ascii=False
                )

            return updated
        else:
            raise Exception("Xenia Manager Not Installed")

    # @staticmethod
    # def find_game_icon(game_folder):
    #     artwork = Path(game_folder) / "Artwork"
    #
    #     if not artwork.exists():
    #         return None
    #
    #     for icon in artwork.glob("*.ico"):
    #         return icon
    #
    #     return None

    def save_game(self, game: Game):
        with self.conn as con:
            con.execute("""
                INSERT INTO games (
                    platform,
                    game_id,
                    title,
                    config_path
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT(platform, game_id)
                DO UPDATE SET
                    title = excluded.title,
                    config_path = excluded.config_path
            """, (
                game.platform,
                game.game_id,
                game.title,
                str(game.config_path) if game.config_path else None,
            ))

            con.execute("""
                INSERT INTO gameplay (
                    platform,
                    game_id,
                    last_played,
                    play_count,
                    play_time
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(platform, game_id)
                DO UPDATE SET
                    last_played = excluded.last_played,
                    play_count = excluded.play_count,
                    play_time = excluded.play_time
            """, (
                game.platform,
                game.game_id,
                game.last_played,
                game.play_count,
                game.play_time,
            ))

            for disc in game.discs:
                con.execute("""
                    INSERT INTO discs (
                        platform,
                        game_id,
                        media_id,
                        file_path,
                        disc_count,
                        disc_type,
                        disc_swap_required,
                        disc_number,
                        label
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(platform, game_id, disc_number)
                    DO UPDATE SET
                        media_id = excluded.media_id,
                        file_path = excluded.file_path,
                        disc_count = excluded.disc_count,
                        disc_type = excluded.disc_type,
                        disc_swap_required = excluded.disc_swap_required,
                        label = excluded.label
                """, (
                    game.platform,
                    game.game_id,
                    disc.media_id,
                    str(disc.file_path) if disc.file_path else None,
                    disc.disc_count,
                    disc.disc_type,
                    int(disc.disc_swap_required),
                    disc.disc_number,
                    disc.label,
                ))

    from typing import Literal

    def import_games_from_source(self, source: GameSource, xbox_game_list: list[XboxRom] | None = None, log_callback=None, indie_game_list: list[XBLIGGame] | None = None,):
        config = load_config_file()

        if source == "indie":
            assert indie_game_list is not None
            imported_games = indie_game_list
            message = (
                f"Imported {len(imported_games)} {source} Games from Folders"
            )
        elif source == "xemu":
            self.compatibility = load_xemu_compatibility()
            if xbox_game_list is None:
                xbox_game_list = []
            imported_games = [
                create_xbox_game(game, compatibility=self.compatibility)
                for game in xbox_game_list
            ]

            message = (
                f"Imported {len(imported_games)} .xiso Games from Folders"
            )

        elif source == "xenia_manager":
            if not config["xenia_manager_installed"]:
                raise Exception("Xenia Manager Not Installed")

            games_json = Path("config") / "games.json"
            games_json_path = (
                    Path(config["xenia_manager_path"]) / games_json
            )

            if not games_json_path.exists():
                raise FileNotFoundError(games_json_path)

            backup_path = get_app_dir() / "config" / "games.json"

            shutil.copy2(
                games_json_path,
                backup_path,
            )

            if log_callback:
                log_callback(
                    f"Copied {games_json_path} to {backup_path}"
                )

            with open(games_json_path, "r", encoding="utf-8") as f:
                source_games = json.load(f)

            # if len(source_games) == len(self.games):
            #     message = f"Import Not Required {len(source_games)} games"
            #
            #     if log_callback:
            #         log_callback(message)
            #
            #     return

            imported_games = [
                create_xbox360_game_from_xenia_manager(game)
                for game in source_games
            ]

            message = (
                f"Imported {len(imported_games)} "
                f"Games from Xenia Manager"
            )

        elif source == "xenia_edge":
            if not config["xenia_edge_installed"]:
                raise Exception("Xenia Edge Not Installed")

            source_games = import_edge_games(
                log_callback=log_callback
            )

            # if len(source_games) == len(self.games):
            #     message = f"Import Not Required {len(source_games)} games"
            #
            #     if log_callback:
            #         log_callback(message)
            #
            #     return

            imported_games = [
                create_xbox360_game_from_edge(game)
                for game in source_games
            ]

            message = (
                f"Imported {len(imported_games)} "
                f"Games From Edge"
            )

        else:
            raise ValueError(f"Unknown game source: {source}")

        # ----------------------------------------
        # Database
        # ----------------------------------------

        failed_games = []

        for game in imported_games:
            try:
                self.add_game(game)
            except Exception as e:
                failed_games.append((game, e))

                logger.exception(
                    "Failed to add game: %r\nError: %s",
                    game,
                    e,
                )

        if failed_games:
            logger.warning(
                "Failed to add %d of %d games",
                len(failed_games),
                len(imported_games),
            )
        # ----------------------------------------
        # Multi-disc information
        # ----------------------------------------

        if source == "xenia_manager" or source == "xenia_edge":
            multidisc_info = get_app_dir() / "config" / "disc-info.json"
            self.import_multidisc_json(
                multidisc_info,
                log_callback=log_callback,
            )

        if log_callback:
            log_callback(message)

    def add_game(self, game: Game):

        platform = game.platform.value

        config_path = getattr(game, "config_path", None)
        emulator = getattr(game, "emulator", None)
        discs = getattr(game, "discs", [])

        with self.conn as con:

            # ----------------------------------------
            # Game
            # ----------------------------------------

            con.execute("""
                INSERT INTO games (
                    platform,
                    game_id,
                    title,
                    config_path
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT(platform, game_id)
                DO UPDATE SET
                    title = excluded.title,
                    config_path = excluded.config_path
            """, (
                platform,
                game.game_id,
                game.title,
                str(config_path) if config_path else None,
            ))

            # ----------------------------------------
            # Gameplay
            # ----------------------------------------

            con.execute("""
                INSERT INTO gameplay (
                    platform,
                    game_id,
                    last_played,
                    play_count,
                    play_time
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(platform, game_id)
                DO UPDATE SET
                    last_played = excluded.last_played,
                    play_count = excluded.play_count,
                    play_time = excluded.play_time
            """, (
                platform,
                game.game_id,
                game.last_played,
                game.play_count,
                game.play_time,
            ))

            # ----------------------------------------
            # Discs
            # ----------------------------------------

            for disc in discs:
                con.execute("""
                    INSERT INTO discs (
                        platform,
                        game_id,
                        media_id,
                        file_path,
                        disc_count,
                        disc_type,
                        disc_swap_required,
                        disc_number,
                        label
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(platform, game_id, disc_number)
                    DO UPDATE SET
                        media_id = excluded.media_id,
                        file_path = excluded.file_path,
                        disc_count = excluded.disc_count,
                        disc_type = excluded.disc_type,
                        disc_swap_required = excluded.disc_swap_required,
                        label = excluded.label
                """, (
                    platform,
                    game.game_id,
                    disc.media_id,
                    str(disc.file_path) if disc.file_path else None,
                    disc.disc_count,
                    disc.disc_type,
                    int(disc.disc_swap_required),
                    disc.disc_number,
                    disc.label,
                ))

            # ----------------------------------------
            # Emulator
            # ----------------------------------------

            if emulator:
                version = getattr(game, "emulator_version", None)

                con.execute("""
                    INSERT INTO emulators (
                        platform,
                        emulator,
                        version
                    )
                    VALUES (?, ?, ?)
                    ON CONFLICT(platform, emulator)
                    DO UPDATE SET
                        version = excluded.version
                """, (
                    platform,
                    emulator,
                    version,
                ))

                con.execute("""
                    INSERT INTO compatibility (
                        platform,
                        game_id,
                        emulator
                    )
                    VALUES (?, ?, ?)
                    ON CONFLICT(platform, game_id, emulator)
                    DO UPDATE SET
                        compatibility_updated = CURRENT_TIMESTAMP
                """, (
                    platform,
                    game.game_id,
                    emulator,
                ))

    def search_games(self, search_text=""):
        with self.conn as con:
            query = """
            SELECT *
            FROM games
            """

            params = ()

            if search_text:
                query += " WHERE title LIKE ?"
                params = (f"%{search_text}%",)

            query += " ORDER BY title"

            return [dict(row) for row in con.execute(query, params)]

    def get_discs(self, title_id):
        with self.conn as con:
            return con.execute("""
            SELECT *
            FROM discs
            WHERE title_id = ?
            ORDER BY disc_number
            """, (
                title_id,
            )).fetchall()
