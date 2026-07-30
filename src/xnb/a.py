from dataclasses import dataclass


class TextureReader:
    pass


class SoundReader:
    pass


class SpriteFontReader:
    pass


READERS = {
    "Microsoft.Xna.Framework.Content.Texture2DReader": TextureReader(),
    "Microsoft.Xna.Framework.Content.SoundEffectReader": SoundReader(),
    "Microsoft.Xna.Framework.Content.SpriteFontReader": SpriteFontReader(),
}


class XNBFile:

    def __init__(self, filename):
        self.filename = filename

        with open(filename, "rb") as f:
            reader = BinaryReader(f)

            if reader.read(3) != b"XNB":
                raise ValueError("Not an XNB file")
            platform_byte = chr(reader.byte())

            try:
                platform = Platform(platform_byte)
            except ValueError:
                platform = Platform.UNKNOWN

            self.header = XNBHeader(
                platform=platform,
                version=reader.byte(),
                flags=reader.byte(),
                file_size=reader.uint32()
            )
            self.payload = f.read()

        if self.header.compressed:
            self.decompressed_size = int.from_bytes(
                self.payload[:4],
                "little"
            )

            self.compressed_data = self.payload[4:]

        if self.header.compressed:
            decoder = LZXDecompressor()

            self.content = decoder.decompress(
                self.compressed_data,
                self.decompressed_size
            )
        else:
            self.content = self.payload

from enum import Enum

class Platform(Enum):
    WINDOWS = "w"
    XBOX360 = "x"
    WINDOWS_PHONE = "m"
    UNKNOWN = "?"

@dataclass(slots=True)
class XNBHeader:
    platform: Platform
    version: int
    flags: int
    file_size: int

    @property
    def compressed(self):
        return bool(self.flags & 0x80)

    @property
    def hidef(self):
        return bool(self.flags & 0x01)

    def __str__(self):
        return (
            f"{self.platform.name} "
            f"v{self.version} "
            f"{'Compressed' if self.compressed else 'Uncompressed'} "
            f"{'HiDef' if self.hidef else 'Reach'}"
        )

class XNBDecompressor:

    def decompress(self, data: bytes, size: int) -> bytes:
        raise NotImplementedError

class LZXDecompressor(XNBDecompressor):

    def decompress(self, data: bytes, size: int) -> bytes:
        # TODO: implement LZX
        return b""

class XNBCompressionHeader:

    def __init__(self, data):
        self.compressed_size = int.from_bytes(
            data[0:4],
            "little"
        )

        self.decompressed_size = int.from_bytes(
            data[4:8],
            "little"
        )

    def __str__(self):
        return (
            f"Compressed: {self.compressed_size}\n"
            f"Decompressed: {self.decompressed_size}"
        )

class BinaryReader:
    def __init__(self, fp):
        self.fp = fp

    def read(self, count: int) -> bytes:
        return self.fp.read(count)

    def byte(self) -> int:
        return self.read(1)[0]

    def uint16(self) -> int:
        return int.from_bytes(self.read(2), "little")

    def uint32(self) -> int:
        return int.from_bytes(self.read(4), "little")

    def int32(self) -> int:
        return int.from_bytes(self.read(4), "little", signed=True)

    def string(self) -> str:
        length = self.seven_bit_int()
        return self.read(length).decode("utf-8")

    def seven_bit_int(self) -> int:
        value = 0
        shift = 0

        while True:
            b = self.byte()
            value |= (b & 0x7F) << shift

            if (b & 0x80) == 0:
                return value

            shift += 7


xnb = XNBFile("MainMenu.xnb")
# print(xnb.header)
# print(xnb.header.platform)
# print(xnb.header.compressed)
#
# print(hex(xnb.header.flags))
# print(xnb.header.file_size)
#
# print("Payload size:", len(xnb.payload))
# print("First 32 bytes:")
# print(xnb.payload[:32].hex(" "))
#
# compression = XNBCompressionHeader(xnb.payload)
#
# print(compression)
#
# print(xnb.payload[:64].hex(" "))
# print(list(xnb.payload[:16]))

print(xnb.header)
print("Compressed stream:", len(xnb.compressed_data))
print("Expected output:", xnb.decompressed_size)

print(xnb.decompressed_size)
print(len(xnb.compressed_data))
