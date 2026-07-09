from itertools import count
from pathlib import Path

import requests
from packaging.version import parse

import os
import requests
import subprocess
from config import get_app_dir, load_config, save_config
from extract import extract_archives


def download_file(url, path, progress_callback=None, print_debug:bool=False):
    path = Path(path)

    if path.is_dir():
        raise ValueError(f"{path} is a directory, expected a file path.")

    path.parent.mkdir(parents=True, exist_ok=True)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/138.0.0.0 Safari/537.36"
        ),
        "Referer": "https://archive.org/",
        "Accept": "*/*",
    }
    import json
    import requests

    with open("assets/archive.txt", encoding="utf-8") as f:
        data = json.load(f)

    cookies = {
        c["name"]: c["value"]
        for c in data
        if c["name"] in ("logged-in-user", "logged-in-sig")
    }

    r = requests.get(url, headers=headers, cookies=cookies, stream=True)
    if print_debug:
        print(r.status_code)
        print(r.headers.get("Content-Type"))
        print(r.headers.get("Content-Length"))
        print(r.status_code)
        print(r.url)
        print(r.text[:1000])

    r.raise_for_status()
    total = int(r.headers.get("Content-Length", 0))
    done = 0

    with open(path, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            if not chunk:
                continue

            f.write(chunk)
            done += len(chunk)

            if progress_callback:
                progress_callback(done=done, total=total)


class Updater:
    def __init__(self):
        print("Hello")
        # self.config = load_config()
        # self.new_version = None
        # self.edge_version = self.config["edge_version"]
        # self.latest_version = None
        # self.download_path = get_app_dir()
        # self.current_portable_version = self.config["current_portable_version"]

    def check_for_updates(self, log_call_back=None):
        # updater = Updater()
        config = load_config()

        def log(message: str):
            if log_call_back:
                log_call_back(message)
            else:
                print(message)

        def install_update(version_key, install_path, latest_version, asset_url, asset_name):
            asset_path = Path(install_path) / asset_name

            log(f"Downloading {asset_name}...")
            download_file(asset_url, asset_path)

            log(f"Extracting {asset_name}...")
            if extract_archives(install_path) == 1:
                config[version_key] = latest_version
                save_config(config)
                log(f"Updated to {latest_version}")
            else:
                log(f"Failed to update to {latest_version}")

        edge_path = Path(config["xenia_edge_path"])
        portable_path = Path(config["xenia_portable_path"])

        edge_version = config["edge_version"]
        edge_github_version = self.get_github_release_version(
            "https://api.github.com/repos/has207/xenia-edge/releases/latest"
        )

        portable_version = config["current_portable_version"]
        portable_github_version = self.get_github_release_version(
            "https://api.github.com/repos/mortlockpaul-arch/xenia-game-manager/releases/latest"
        )

        log(f"Edge version: {edge_version}")
        log(f"Latest Edge version: {edge_github_version}")
        log(f"Portable version: {portable_version}")
        log(f"Latest Portable version: {portable_github_version}")

        # Edge
        edge_github_url = config["xenia_edge_url"]
        result = self.check_for_github_update(
            edge_github_url, current_version=edge_version)

        if result:
            latest_version, asset_url = result
            install_update(
                "edge_version",
                edge_path,
                latest_version,
                asset_url,
                "xenia.zip",
            )
        else:
            log("No Edge update available")

        # Portable
        xenia_game_manager_url = config["xenia_game_manager_url"]
        result = self.check_for_github_update(
            xenia_game_manager_url,current_version=portable_version)

        if result:
            latest_version, asset_url = result
            install_update(
                "current_portable_version",
                portable_path,
                latest_version,
                asset_url,
                "xenia-game-manager-portable.zip",
            )
        else:
            log("No Xenia Game Manager update available")

    def get_github_release_version(self, url):
        data = requests.get(
            url,
            timeout=10,

        ).json()
        version: str = data["tag_name"]
        return version

    def check_for_github_update(self, url: str, current_version: str, asset_index: int = 0):
        try:
            response = requests.get(url, timeout=1000)
            response.raise_for_status()

            data = response.json()

            version = data["tag_name"].lstrip("v")

            if version == current_version:
                return None

            assets = data.get("assets", [])
            if asset_index >= len(assets):
                return None

            return version, assets[asset_index]["browser_download_url"]

        except requests.RequestException:
            return None

    def run_update(self, url):
        path = f"{self.download_path}/{self.latest_version}.msi"
        download_file(url, self.download_path)
        subprocess.Popen(["msiexec", "/i", path, "/passive"])

if __name__ == "__main__":
    print("Hello")
    # updater = Updater()
    # EDGE_RELEASE = "https://github.com/has207/xenia-edge/releases"
    #
    # CONFIG = load_config()
    # EDGE_PATH = Path(CONFIG["xenia_edge_path"])
    # ASSET_PATH = EDGE_PATH / "xenia.zip"
    # EDGE_VERSION = CONFIG["edge_version"]
    # current_portable_version = CONFIG["current_portable_version"]
    # result = updater.check_for_edge_update(EDGE_VERSION)
    # if result:
    #     LATEST_VERSION, ASSET_URL = result
    #     download_file(ASSET_URL, ASSET_PATH)
    #     count = extract_archives(EDGE_PATH)
    #     if count == 1:
    #         CONFIG["edge_version"] = LATEST_VERSION
    #         save_config(CONFIG)
    #     print(LATEST_VERSION, ASSET_URL)
    # else:
    #     print("No edge update available")
    # result = updater.check_for_xenia_game_manager_update(
    #     "https://api.github.com/repos/mortlockpaul-arch/xenia-game-manager/releases/latest")
    # if result:
    #     LATEST_VERSION, ASSET_URL = result
    #     print(LATEST_VERSION, ASSET_URL)
    #     EDGE_VERSION = updater.get_github_release_version(
    #         "https://api.github.com/repos/has207/xenia-edge/releases/latest")
    # else:
    #     print("No Xenia Game Manager update available")