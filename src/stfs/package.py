import struct
from pathlib import Path

from config import get_app_dir

CONTENT_TYPE_STRINGS = {
    "00000001": "Saved Game",
    "00000002": "Marketplace DLC",
    "00004000": "Installed Game",
    "00007000": "Games on Demand",
    "000B0000": "Title Update",
    "000D0000": "Xbox Live Indie Game",
}

import struct


class STFSVolume:
    """
    STFS volume descriptor.
    Handles block addressing.
    """

    def __init__(self, file):
        self.file = file

        #
        # Read volume descriptor
        #
        file.seek(0x379)

        self.descriptor = struct.unpack(
            ">B",
            file.read(1)
        )[0]

        #
        # STFS block size
        #
        # Xbox 360 STFS uses 0x1000 byte blocks
        #
        self.block_size = 0x1000

        #
        # Determine block shift
        #
        if self.descriptor == 0:
            self.block_shift = 0x0A
        elif self.descriptor == 1:
            self.block_shift = 0x0B
        else:
            self.block_shift = 0x0C


    def block_offset(self, block):
        """
        Convert an STFS block number
        into a file offset.
        """

        return (
            block << self.block_shift
        )

class STFSFile:
    def __init__(self, name, path, size, first_block, is_directory=False):
        self.name = name
        self.path = path
        self.size = size
        self.first_block = first_block
        self.is_directory = is_directory

    def __repr__(self):
        kind = "DIR" if self.is_directory else "FILE"
        return f"<{kind} {self.path} ({self.size} bytes)>"

class STFSPackage:

    @property
    def content_type_hex(self):
        return f"{self.content_type:08X}"

    @property
    def content_type_name(self):
        return CONTENT_TYPE_STRINGS.get(
            self.content_type_hex,
            "Unknown"
        )

    @property
    def block_size(self):
        return self.volume.block_size

    def __init__(self, path):
        self.path = Path(path)
        self.file = open(
            self.path,
            "rb"
        )

        self._read_header(path)
        self.files = self.read_file_table()

    def _read_header(self, path):
        self.volume = STFSVolume(
            self.file
        )

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

            raw_name = f.read(0x80)

            self.display_name = (
                raw_name
                .decode("utf-16-be", errors="ignore")
                .split("\x00")[0]
            )

    def read_file_table(self):
        """
        Read STFS file entries.
        """

        files = []

        # File table starts at block stored in header
        self.file.seek(0x37D)

        root_block = int.from_bytes(
            self.file.read(3),
            "big"
        )

        if root_block == 0:
            return files

        offset = self.volume.block_offset(
            root_block
        )

        self.file.seek(offset)

        while True:

            entry = self.file.read(0x40)

            if len(entry) != 0x40:
                break

            # empty entry
            if entry[0] == 0:
                continue

            name = (
                entry[0:0x28]
                .split(b"\x00")[0]
                .decode(
                    "ascii",
                    errors="ignore"
                )
            )

            if not name:
                continue

            flags = entry[0x28]

            is_directory = bool(
                flags & 0x80
            )

            first_block = int.from_bytes(
                entry[0x2F:0x32],
                "big"
            )

            size = int.from_bytes(
                entry[0x32:0x36],
                "big"
            )

            files.append(
                STFSFile(
                    name,
                    name,
                    size,
                    first_block,
                    is_directory
                )
            )

        return files

    @property
    def title_id_hex(self):
        return f"{self.title_id:08X}"

    @property
    def media_id_hex(self):
        return f"{self.media_id:08X}"
from pathlib import Path
import xml.etree.ElementTree as ET

from pathlib import Path
import xml.etree.ElementTree as ET

STFS_MAGIC = {b"CON ", b"LIVE", b"PIRS"}

from pathlib import Path
import xml.etree.ElementTree as ET


STFS_MAGIC = {
    b"CON ",
    b"LIVE",
    b"PIRS",
}


def find_xblig_packages(root: str | Path):

    root = Path(root)
    games = []

    def is_stfs(path: Path):
        try:
            with path.open("rb") as f:
                return f.read(4) in STFS_MAGIC
        except Exception:
            return False

    def parse_xml(xml_file: Path):

        data = {}

        if not xml_file or not xml_file.exists():
            return data

        try:
            tree = ET.parse(xml_file)
            root_xml = tree.getroot()

            title_info = root_xml.find(".//TitleInfo")

            if title_info is not None:

                # Main title attribute
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

                description = title_info.findtext(
                    "Description"
                )

                if description:
                    data["description"] = description.strip()

            # Localized title fallback
            if not data.get("title"):

                title = root_xml.find(
                    ".//TitleName"
                )

                if title is not None:
                    data["title"] = title.text.strip()


        except Exception as e:
            print(
                f"XML parse error {xml_file}: {e}"
            )

        return data


    for package in root.rglob("*"):

        if not package.is_file():
            continue

        if not is_stfs(package):
            continue


        # Example:
        # 584E07D2
        #    00000002
        #       HASH
        #
        title_id = None
        content_type = None

        try:
            content_type = package.parent.name
            title_id = package.parent.parent.name
        except Exception:
            pass


        extracted = package.parent / f"{package.name}_extracted"


        game_root = None
        exe_file = None

        if extracted.exists():

            for exe in extracted.rglob("*.exe"):
                exe_file = exe
                game_root = exe.parent
                break


        game_info = extracted / "GameInfo.xml"




        dashboard_icon = None
        title_image = None


        if extracted.exists():

            icon = extracted / "DashboardIcon.png"
            image = extracted / "TitleImage.png"

            if icon.exists():
                dashboard_icon = icon

            if image.exists():
                title_image = image

        xml_data = parse_xml(game_info)

        title = (
                xml_data.get("Title")
                or xml_data.get("TitleName")
                or xml_data.get("DisplayName")
                or package.stem
        )

        games.append({
            "title": title,
            "title_id": title_id,
            "content_type": content_type,

            "content_name": "Xbox Live Indie Game",

            "package": package,

            "extracted": (
                extracted
                if extracted.exists()
                else None
            ),

            "game_root": game_root,

            "exe": exe_file,

            "xml": (
                game_info
                if game_info.exists()
                else None
            ),

            "dashboard_icon": dashboard_icon,

            "title_image": title_image,

            **xml_data,

        })


    return games

import xml.etree.ElementTree as ET


def read_bytes(file_path: Path):
    with open(file_path, "rb") as f:
        from pathlib import Path

        data = Path(file_path).read_bytes()

        for word in [b"XNA", b"Xbox", b"default.xex", b"Content"]:
            if word in data:
                print("Found:", word.decode())

if __name__ == "__main__":
    games = find_xblig_packages(get_app_dir() / "downloads" / "xblig")

    print(f"\nFound {len(games)} Xbox Live Indie Games\n")

    for i, game in enumerate(games, 1):
        print("=" * 80)
        print(f"Game #{i}")
        print("=" * 80)

        print(f"Title        : {game.get('title')}")
        print(f"Title ID     : {game.get('title_id')}")
        print(f"Content Type : {game.get('content_type')} ({game.get('content_name')})")
        print(f"Publisher    : {game.get('publisher')}")
        print(f"Description  : {game.get('description')}")

        print()
        print(f"Package      : {game.get('package')}")
        print(f"Extracted    : {game.get('extracted')}")
        print(f"Game Root    : {game.get('game_root')}")
        print(f"Executable   : {game.get('exe')}")
        print(f"XML          : {game.get('xml')}")
        print(f"Dashboard    : {game.get('dashboard_icon')}")
        print(f"Title Image  : {game.get('title_image')}")

        print()

    exe = Path(get_app_dir() / "downloads/xblig/Alien Jelly (World) (XBLIG)/584E07D2/00000002/62F2648203AAB1C526B538091DF3BBE8CFC6E7E758_extracted/584E07D1/Game.exe")
    read_bytes(exe)
