# utils.py
import os

from config import load_config, load_xenia_manager_config, get_app_dir

KEEP_UPPER = {
    "DLC", "HD", "XBLA", "USA", "PAL",
    "NTSC", "GTA", "NBA", "NHL", "UFC",
    "FIFA", "MX", "ATV", "II", "III", "UGC", "NFS", "IL"
}


def smart_title_case(title):
    title = re.sub(r"\s*\(\d+\)$", "", title)
    title = re.sub(r"\s+", " ", title).strip()

    words = []

    for word in title.split():

        # already normal mixed case
        if not word.isupper():
            words.append(word)
            continue

        # preserve acronyms
        if word in KEEP_UPPER:
            words.append(word)
            continue

        # convert shouting words
        words.append(word.capitalize())

    return " ".join(words)

from pathlib import Path
import shutil
from pathlib import Path
import shutil

def xenia_edge_optimise_settings(log_callback = None):

    datadir = Path(get_app_dir())
    config_dir = datadir / "assets" / "settings"

    # current user folder (C:\Users\<you>\Documents\Xenia\config)
    edge_settings = Path.home() / "Documents" / "Xenia" / "config"

    edge_settings.mkdir(parents=True, exist_ok=True)

    for toml_file in config_dir.glob("*.toml"):
        destination = edge_settings / f"{toml_file.stem}.config.toml"
        shutil.copy2(toml_file, destination)
        if log_callback is None:
            print(f"Copied {toml_file.name} -> {destination.name}")
        else:
            log_callback(f"Copied {toml_file.name} -> {destination.name}")

import re

DISC_PATTERNS = [
    r"\(\s*(?:disc|disk|dvd|cd)\s*(\d+)\s*\)",
    r"(?:disc|disk|dvd|cd)\s*(\d+)",
]


def detect_disc_number(title: str):
    """
    Returns the detected disc number.
    Returns 1 if no disc number is present.
    """

    if not title:
        return 1

    for pattern in DISC_PATTERNS:
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            return int(match.group(1))

    return 1


def strip_disc_suffix(title: str):
    """
    Examples:
        Lost Odyssey (Disc 1) -> Lost Odyssey
        Lost Odyssey Disc 2   -> Lost Odyssey
        Lost Odyssey - DVD 1  -> Lost Odyssey
        Lost Odyssey: CD 3    -> Lost Odyssey
    """

    if not title:
        return ""

    title = re.sub(
        r"\s*[\(\[]?\s*[-:]?\s*(?:disc|disk|dvd|cd)\s*\d+\s*[\)\]]?\s*$",
        "",
        title,
        flags=re.IGNORECASE,
    )

    return title.strip()

def is_install_disc(label: str):
    if not label:
        return False

    label = label.lower()

    return any(
        word in label
        for word in [
            "install",
            "data",
            "content"
        ]
    )


def is_multiplayer_disc(label: str):
    if not label:
        return False

    label = label.lower()

    return "multiplayer" in label


def disc_role(label: str):
    """
    Human readable disc role.
    """

    if not label:
        return "Unknown"

    if is_install_disc(label):
        return "Install"

    if is_multiplayer_disc(label):
        return "Multiplayer"

    return "Story"


DISC_TYPE_LABELS = {
    "story_swap": "Story Campaign",
    "install_play": "Install + Play",
    "campaign_multiplayer": "Campaign + Multiplayer",
    "hybrid_story_content": "Hybrid Content",
    "play_install": "Install Disc",
}


def format_disc_type(disc_type: str):
    return DISC_TYPE_LABELS.get(
        disc_type,
        disc_type or "Single Disc"
    )


def star(value):
    try:
        return "⭐" if int(value) == 1 else "☆"
    except Exception:
        return "☆"


def format_play_count(count):
    try:
        count = int(count)
    except Exception:
        count = 0

    return f"{count:,}"


def sort_title(title):
    """
    Ignore 'The' when sorting.
    """

    if not title:
        return ""

    lower = title.lower()

    if lower.startswith("the "):
        return lower[4:]

    return lower


import re

XUID_PATTERN = re.compile(r"^E[0-9A-Fa-f]{15}$")

from pathlib import Path

CONTENT_ROOT = Path(
    r"D:\RetroBat\emulators\xenia-manager\Emulators\Content"
)

CONTENT_TYPES = {
    0x00000001: "Xbox Arcade",
    0x00000002: "DLC",
    0x00004000: "Saved Game",
    0x00010000: "Profile",
    0x00020000: "Gamer Picture",
    0x00030000: "Theme",
    0x00090000: "Avatar Item",
    0x000B0000: "Title Update",
}

from pathlib import Path
import struct


class STFSPackage:
    def __init__(self, path):
        self.path = Path(path)

        with open(path, "rb") as f:
            self.magic = f.read(4).decode(
                "ascii",
                errors="ignore"
            )

            if self.magic not in (
                    "CON ",
                    "LIVE",
                    "PIRS"
            ):
                raise ValueError(
                    "Not an STFS package"
                )

            #
            # Content Type
            #

            f.seek(0x344)

            self.content_type = struct.unpack(
                ">I",
                f.read(4)
            )[0]

            #
            # Title ID
            #

            f.seek(0x360)

            self.title_id = struct.unpack(
                ">I",
                f.read(4)
            )[0]

            #
            # Media ID
            #

            f.seek(0x36C)

            self.media_id = struct.unpack(
                ">I",
                f.read(4)
            )[0]

            #
            # Display name
            #

            f.seek(0x411)

            self.display_name = (
                f.read(0x80)
                .decode(
                    "utf-16-be",
                    errors="ignore"
                )
                .rstrip("\x00")
            )

    @property
    def title_id_hex(self):
        return f"{self.title_id:08X}"

    @property
    def media_id_hex(self):
        return f"{self.media_id:08X}"


def read_stfs_header(path):
    with open(path, "rb") as f:
        # Package magic
        magic = f.read(4).decode("ascii", errors="ignore")

        if magic not in ("CON ", "LIVE", "PIRS"):
            return None

        # Title ID
        f.seek(0x360)
        title_id = struct.unpack(">I", f.read(4))[0]

        # Display name
        f.seek(0x411)
        display_name = (
            f.read(0x80)
            .decode("utf-16-be", errors="ignore")
            .strip("\x00")
        )

        # Content type
        f.seek(0x344)
        content_type = struct.unpack(">I", f.read(4))[0]

        return {
            "magic": magic.strip(),
            "title_id": f"{title_id:08X}",
            "content_type": content_type,
            "content_name": CONTENT_TYPES.get(
                content_type,
                f"Unknown ({content_type:08X})"
            ),
            "display_name": display_name,
        }


def get_content_info(contend_dir: Path):
    for file in CONTENT_ROOT.rglob("*"):
        if not file.is_file():
            continue

        try:
            info = read_stfs_header(file)

            if info:
                print(
                    f"{file.name}\n"
                    f"  Type: {info['content_name']}\n"
                    f"  Title ID: {info['title_id']}\n"
                    f"  Name: {info['display_name']}\n"
                )

        except Exception:
            pass


def detect_profiles(content_dir: Path):
    profiles = []

    if not content_dir.exists():
        return profiles

    for folder in content_dir.iterdir():
        if not folder.is_dir():
            continue

        if XUID_PATTERN.match(folder.name):
            profiles.append({
                "xuid": folder.name,
                "path": folder,
            })

    return sorted(profiles, key=lambda p: p["xuid"])


import shutil
from pathlib import Path


def install_title_update(
        stfs_file,
        xenia_content_root):
    pkg = STFSPackage(stfs_file)

    if pkg.content_type != 0x000B0000:
        raise ValueError(
            "Not a title update"
        )

    dest = (
            Path(xenia_content_root)
            / "0000000000000000"
            / pkg.title_id_hex
            / "000B0000"
    )

    dest.mkdir(
        parents=True,
        exist_ok=True
    )

    shutil.copy2(
        stfs_file,
        dest / Path(stfs_file).name
    )

    return dest

import json
from difflib import unified_diff

import json


def show_game_diff(file1, file2):
    with open(file1, encoding="utf-8") as f:
        old_games = json.load(f)

    with open(file2, encoding="utf-8") as f:
        new_games = json.load(f)

    def key(game):
        return game["game_id"], game["media_id"]

    old = {key(g): g for g in old_games}
    new = {key(g): g for g in new_games}

    added = new.keys() - old.keys()
    removed = old.keys() - new.keys()
    common = old.keys() & new.keys()

    print(f"Added: {len(added)}")
    for k in sorted(added):
        g = new[k]
        print(f"  + {g['title']} ({g['game_id']} / {g['media_id']})")

    print(f"\nRemoved: {len(removed)}")
    for k in sorted(removed):
        g = old[k]
        print(f"  - {g['title']} ({g['game_id']} / {g['media_id']})")

    print("\nModified:")
    for k in sorted(common):
        before = old[k]
        after = new[k]

        changes = []

        for field in sorted(set(before) | set(after)):
            if before.get(field) != after.get(field):
                changes.append(field)

        if changes:
            print(f"* {after['title']}: {', '.join(changes)}")

config = load_config()
xenia_manager_path = Path(config["xenia_manager_path"])

show_game_diff(
    xenia_manager_path / "config" / "games.json.backup",
    xenia_manager_path / "config" / "games.json",
)

    #
    # config = load_config()
    # xenia_manager_installed = config["xenia_manager_installed"]
    # if xenia_manager_installed:
    #     xenia_manager_path = Path(config["xenia_manager_path"])
    #     xenia_manager_config = load_xenia_manager_config(xenia_manager_path)
    #
    #     unified_content: bool = (xenia_manager_config["emulators"]["settings"]["unified_content"])
    #     xenia_path = Path(xenia_manager_config["emulators"]["canary"]["executable_location"])
    #     xenia_emulator_location = Path(xenia_manager_config["emulators"]["canary"]["emulator_location"])
    #     emulators_dir = Path(xenia_emulator_location).parent
    #     if unified_content:
    #         xenia_content_folder = Path.joinpath(xenia_manager_path, emulators_dir, "Content")
    #     else:
    #         xenia_content_folder = Path.joinpath(xenia_emulator_location, "content")
    #
    #     profile_info = detect_profiles(xenia_content_folder)
    #
    #     for profile in profile_info:
    #         xuid = profile["xuid"]
    #         profile_path = Path(profile["path"])
    #         account_path = (
    #                 profile_path
    #                 / "FFFE07D1"
    #                 / "00010000"
    #                 / xuid
    #                 / "Account"
    #         )
    #         print(xuid)
    #         print(profile_path)
    #         print(account_path)
    # else:
    #     print("Xenia Manager is not installed")
    #
    # xenia_edge_optimise_settings()