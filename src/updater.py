from pathlib import Path

import requests
from packaging.version import parse

import os
import requests
import subprocess
from config import get_app_dir, load_config, save_config

class Updater:
    def __init__(self):

        self.config = load_config()
        self.new_version = None
        self.edge_version = self.config["edge_version"]
        self.latest_version = None
        self.download_path = get_app_dir()
        self.current_version = self.config["current_version"]

    def get_edge_version(self):
        data = requests.get(
            "https://api.github.com/repos/has207/xenia-edge/releases/latest"
        ).json()

        self.edge_version: str = data["tag_name"]
        return self.edge_version

    def check_for_update(self):
        data = requests.get(
            "https://api.github.com/repos/mortlockpaul-arch/xenia-game-manager/releases/latest"
        ).json()

        self.new_version = data["tag_name"].lstrip("v")

        if parse(self.new_version) > parse(self.current_version):
            asset_url = data["assets"][0]["browser_download_url"]

            return self.new_version, asset_url

        return None

    def check_for_edge_update(self, edge_version: str):
        try:
            response = requests.get(
                "https://api.github.com/repos/has207/xenia-edge/releases/latest",
                timeout=10
            )
            response.raise_for_status()

            data = response.json()

            self.latest_version:str = data["tag_name"].lstrip("v")

            if self.latest_version != edge_version:
                assets = data.get("assets", [])
                asset_url = assets[2]["browser_download_url"] if assets else None
                return self.latest_version, asset_url

        except requests.RequestException:
            pass

        return None


    def download_file(self, url, path):
        r = requests.get(url, stream=True)
        with open(path, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)

    def run_update(self, url):
        path = f"{self.download_path}/{self.latest_version}.msi"
        self.download_file(url, self.download_path)
        subprocess.Popen(["msiexec", "/i", path, "/passive"])

if __name__ == "__main__":
    updater = Updater()
    EDGE_RELEASE = "https://github.com/has207/xenia-edge/releases"

    CONFIG = load_config()

    EDGE_VERSION = CONFIG["edge_version"]
    CURRENT_VERSION = CONFIG["current_version"]
    result = updater.check_for_edge_update(EDGE_VERSION)
    if result:
        LATEST_VERSION, ASSET_URL = result
        print(LATEST_VERSION, ASSET_URL)
    else:
        print("No edge update available")
    result = updater.check_for_update()
    if result:
        LATEST_VERSION, ASSET_URL = result
        print(LATEST_VERSION, ASSET_URL)
        EDGE_VERSION = updater.get_edge_version()
    else:
        print("No Xenia Game Manager update available")