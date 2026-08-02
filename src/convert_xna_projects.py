from config import get_app_dir

FNA_VERSION = "25.0.0"

from pathlib import Path
import shutil

DEST = Path("References")

GAC_FOLDERS = [
    Path(r"C:\Windows\assembly"),
    Path(r"C:\Windows\Microsoft.NET\assembly"),
    Path(r"C:\WINDOWS\assembly\GAC_32")
]

from dataclasses import dataclass
import struct

@dataclass
class XNBHeader:
    platform: str
    version: int
    flags: int
    file_size: int

def read_header(f):
    if f.read(3) != b"XNB":
        raise ValueError("Not an XNB")

    platform = f.read(1).decode("ascii")
    version = struct.unpack("<B", f.read(1))[0]
    flags = struct.unpack("<B", f.read(1))[0]
    file_size = struct.unpack("<I", f.read(4))[0]

    return XNBHeader(platform, version, flags, file_size)

# with open("MainMenu.xnb", "rb") as f:
#     header = read_header(f)
#     print(header)

def inspect_xnb():
    with open("MenuWheel.xnb", "rb") as f:
        magic = f.read(3)
        platform = chr(f.read(1)[0])
        version = f.read(1)[0]
        flags = f.read(1)[0]
        size = int.from_bytes(f.read(4), "little")

    print(magic, platform, version, flags, size)

def find_xna_assemblies():
    roots = [
        r"C:\Windows\assembly",
        r"C:\Windows\Microsoft.NET\assembly",
    ]

    assemblies = {}

    for root in roots:
        if not os.path.exists(root):
            continue

        for dirpath, _, filenames in os.walk(root):
            for filename in filenames:
                if filename.startswith("Microsoft.Xna.") and filename.endswith(".dll"):
                    path = Path(dirpath) / filename
                    assemblies.setdefault(filename, []).append(path)

    return assemblies


def method_name():
    assemblies = find_xna_assemblies()
    for name, paths in sorted(assemblies.items()):
        print(name)
        for p in paths:
            print("   ", p)

def copy_xna_assemblies():
    DEST.mkdir(exist_ok=True)

    assemblies = find_xna_assemblies()

    if not assemblies:
        print("No XNA assemblies found.")
        return

    print(f"Found {len(assemblies)} assemblies:\n")

    for name, paths in assemblies.items():
        for src in paths:
            version = src.parent.name.replace("__", "_")
            dst = DEST / version
            dst.mkdir(parents=True, exist_ok=True)

            shutil.copy2(src, dst / name)
            print(f"Copied {name}")
            print(f"    {src}")

    print(f"\nDone. Assemblies copied to {DEST.resolve()}")

def copy_check_xna_assemblies():
    assembly_folder = root / "References"
    if not assembly_folder.exists():
        copy_xna_assemblies()

if __name__ == "__main__":
    # root = get_app_dir()
    # copy_check_xna_assemblies()

    def log(message):
        print(message)

    # project_base = root / "downloads"
    # converter = ConvertXnaProjects(root, log)
    # projects = converter.get_cs_project_folders(project_base)
    #
    # if not projects:
    #     print("No projects found")
    #     exit(1)

    # Error: Could not find reference: Microsoft.Xna.Framework, Version=3.1.0.0, Culture=neutral, PublicKeyToken=51c3bfb2db46012c
