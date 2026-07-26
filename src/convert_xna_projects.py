from pathlib import Path
import xml.etree.ElementTree as ET
import shutil

from config import get_app_dir

FNA_VERSION = "25.0.0"


def convert_xblig_to_fna(project_path):
    """
    Convert an ILSpy decompiled XBLIG XNA project to an FNA project.

    - Changes target framework
    - Removes XNA references
    - Adds FNA NuGet package
    - Keeps local DLL references
    - Backs up original csproj
    """

    project_path = Path(project_path)

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
    # Remove XNA References
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



def convert_folder(folder):
    """
    Convert every csproj below a folder.
    """

    folder = Path(folder)

    projects = list(folder.rglob("*.csproj"))

    print(f"Found {len(projects)} projects")

    for project in projects:
        try:
            convert_xblig_to_fna(project)
            add_xna_compat(project.parent)
        except Exception as e:
            print(
                f"FAILED {project}: {e}"
            )

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

def remove_xna_usings(folder):

    folder = Path(folder)

    for cs in folder.rglob("*.cs"):

        text = cs.read_text(
            encoding="utf-8",
            errors="ignore"
        )

        original = text

        for u in xna_using_files:

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
if __name__ == "__main__":

    convert_folder(get_app_dir() / "downloads")

