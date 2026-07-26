import struct
from pathlib import Path

CONTENT_TYPE_STRINGS = {
    "00000001": "Saved Game",
    "00000002": "Marketplace DLC",
    "00004000": "Installed Game",
    "00007000": "Games on Demand",
    "000B0000": "Title Update",
    "000D0000": "Xbox Live Indie Game",
}

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