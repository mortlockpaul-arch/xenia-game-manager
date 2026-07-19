import os
import shutil
from pathlib import Path


def move_title_update_folders(root_folder, destination_folder,
                              filename_pattern="*.xexp",
                              log_callback=None):
    """
    Find folders containing a title update file and move the entire folder.

    Parameters
    ----------
    root_folder : str | Path
        Folder to search.
    destination_folder : str | Path
        Where matching folders will be moved.
    filename_pattern : str
        Glob pattern identifying a title update file.
    """

    root_folder = Path(root_folder)
    destination_folder = Path(destination_folder)
    destination_folder.mkdir(parents=True, exist_ok=True)

    moved = 0

    for current_dir, dirs, files in os.walk(root_folder, topdown=False):
        current_dir = Path(current_dir)

        if any(current_dir.glob(filename_pattern)):
            destination = destination_folder / current_dir.name

            # Avoid overwriting existing folders
            if destination.exists():
                stem = current_dir.name
                i = 1
                while (destination_folder / f"{stem}_{i}").exists():
                    i += 1
                destination = destination_folder / f"{stem}_{i}"

            shutil.move(str(current_dir), str(destination))
            moved += 1

            if log_callback:
                log_callback(f"Moved: {current_dir} -> {destination}")
            else:
                print(f"Moved: {current_dir} -> {destination}")

    return moved

def remove_empty_folders(root_folder, log_callback=None):
    total_removed = 0

    while True:
        removed_this_pass = 0

        for current_dir, dirs, files in os.walk(root_folder, topdown=False):
            try:
                if not dirs and not files:
                    os.rmdir(current_dir)
                    removed_this_pass += 1
                    total_removed += 1

                    if log_callback:
                        log_callback(f"Removed: {current_dir}")
                    else:
                        print(f"Removed: {current_dir}")

            except OSError:
                pass

        if removed_this_pass == 0:
            break

    return total_removed

if __name__ == "__main__":
    count = move_title_update_folders(
        r"D:\roms\Xbox360",
        r"D:\TitleUpdates",
        "*.tu"
    )
    print(f"Moved {count} folders")

    count = move_title_update_folders(
        r"D:",
        r"D:\TitleUpdates",
        "*.tu"
    )
    print(f"Moved {count} folders")

    count = remove_empty_folders(r"D:\roms\Xbox360")
    print(f"Removed {count} folders")
    count = remove_empty_folders(r"C:\Users\mortl\Downloads")
    print(f"Removed {count} folders")