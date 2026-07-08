import requests
from urllib.parse import quote

ITEMS = [f"XBOX_360_DLC_{i}" for i in range(1, 6)]

def get_archive_files(identifier):
    response = requests.get(f"https://archive.org/metadata/{identifier}")
    response.raise_for_status()

    metadata = response.json()

    files = []
    for f in metadata.get("files", []):
        files.append({
            "archive": identifier,
            "name": f["name"],
            "size": int(f.get("size", 0)),
            "format": f.get("format", ""),
            "url": f"https://archive.org/download/{identifier}/{quote(f['name'])}",
        })

    return files

all_files = []

for item in ITEMS:
    print(f"Fetching {item}...")
    try:
        all_files.extend(get_archive_files(item))
    except requests.HTTPError as e:
        print(f"Failed to fetch {item}: {e}")

print(f"\nFound {len(all_files)} files.")

# Example output
for file in all_files[:10]:
    print(file)