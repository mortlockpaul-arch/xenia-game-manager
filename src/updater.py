import requests
from packaging.version import parse

CURRENT_VERSION = "0.7.3"

def check_for_update():
    data = requests.get(
        "https://api.github.com/repos/mortlockpaul-arch/xenia-game-manager/releases/latest"
    ).json()

    latest_version = data["tag_name"].lstrip("v")

    if parse(latest_version) > parse(CURRENT_VERSION):
        asset_url = data["assets"][0]["browser_download_url"]

        return latest_version, asset_url

    return None

import os
import requests
import subprocess

def download_file(url, path):
    r = requests.get(url, stream=True)
    with open(path, "wb") as f:
        for chunk in r.iter_content(8192):
            f.write(chunk)

def run_update(url):
    path = os.path.join(os.getenv("TEMP"), "update.msi")
    download_file(url, path)

    subprocess.Popen(["msiexec", "/i", path, "/passive"])
    os.exit(0)