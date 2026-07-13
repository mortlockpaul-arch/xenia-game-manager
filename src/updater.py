import subprocess
from pathlib import Path
from urllib.parse import urlparse
import json
import requests

from PySide6.QtCore import QObject, Signal, QThread

from config import load_config, save_config
from extract import extract_archives


class UpdateWorker(QThread):

    log = Signal(str)
    progress = Signal(int, int)
    update_finished = Signal()
    error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.updater = None

    def run(self):

        self.updater = UpdateManager()

        self.updater.log.connect(self.log)
        self.updater.progress.connect(self.progress)
        self.updater.finished.connect(self.update_finished)
        self.updater.error.connect(self.error)

        try:
            self.updater.check_for_updates()

        except Exception as e:
            self.error.emit(str(e))

        finally:
            self.quit()


class UpdateManager(QObject):
    """
    Handles application updates.
    """

    log = Signal(str)
    progress = Signal(int, int)
    finished = Signal()
    error = Signal(str)


    def __init__(self, parent=None):
        super().__init__(parent)

        self.config = load_config()


    def _log(self, message: str):
        self.log.emit(message)


    def _progress(self, done: int, total: int | None):
        self.progress.emit(done, total or 0)
    # ---------------------------------------------------------
    # Utilities
    # ---------------------------------------------------------

    @staticmethod
    def install_msi(msi_path):
        subprocess.Popen(
            [
                "msiexec",
                "/i",
                str(msi_path),
                "/passive"
            ]
        )

    def download_file(self, url, path, print_debug:bool=False, archive_org=True):
        path = Path(path)
        if path.is_dir():
            raise ValueError(f"{path} is a directory, expected a file path.")
        path.parent.mkdir(parents=True, exist_ok=True)
        if archive_org:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/138.0.0.0 Safari/537.36"
                ),
                "Referer": "https://archive.org/",
                "Accept": "*/*",
            }
            with open("assets/archive.txt", encoding="utf-8") as f:
                data = json.load(f)
            cookies = {
                c["name"]: c["value"]
                for c in data
                if c["name"] in ("logged-in-user", "logged-in-sig")
            }
        else:
            # Github
            headers = {
                "User-Agent": "Xenia Game Manager"
            }
            cookies = None

        r = requests.get(url, headers=headers, cookies=cookies, stream=True)
        total = int(r.headers.get("Content-Length", 0))
        self._log(f"Downloading: {path.name} ({self.human_size(total)})")

        if print_debug:
            self._log(str(r.status_code))
            self._log(str(r.headers.get("Content-Type")))
            self._log(str(r.headers.get("Content-Length")))
            self._log(str(r.status_code))
            self._log(str(r.url))
            self._log(r.text[:1000])

        r.raise_for_status()

        total = r.headers.get("Content-Length")
        total = int(total) if total else None

        done = 0

        self._progress(done=done, total=total)

        with open(path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue

                f.write(chunk)
                done += len(chunk)

                self._progress(done=done, total=total)

    @staticmethod
    def human_size(size):
        size = int(size)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"

    @staticmethod
    def get_github_release_version(url):
        data = requests.get(
            url,
            timeout=10,

        ).json()
        version: str = data["tag_name"]
        return version

    @staticmethod
    def check_for_github_update(url: str, current_version: str, asset_index: int = 0):
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

    def check_for_updates(self):

        self._check_component(
            version_key="edge_version",
            install_path=self.config["xenia_edge_path"],
            current_version=self.config["edge_version"],
            github_url=self.config["xenia_edge_url"],
            asset_index=3,
        )

        self._check_component(
            version_key="game_manager_version",
            install_path=self.config["xenia_portable_path"],
            current_version=self.config["game_manager_version"],
            github_url=self.config["xenia_game_manager_url"],
        )

        self.finished.emit()

    def _check_component(
            self,
            version_key,
            install_path,
            current_version,
            github_url,
            asset_index=0,
            asset_name=None,
    ):

        result = self.check_for_github_update(
            url=github_url,
            current_version=current_version,
            asset_index=asset_index,
        )

        if not result:
            self._log("No update available")
            return False

        latest_version, asset_url = result

        if asset_name is None:
            asset_name = Path(
                urlparse(asset_url).path
            ).name

        self._log(f"Update found: {current_version} -> {latest_version}")

        asset_path = (Path(install_path) / asset_name)

        try:
            self.download_file(asset_url, asset_path, archive_org=False,)

        except requests.RequestException as e:
            self.error.emit(f"Download failed: {e}")
            return False

        self._log(f"Extracting {asset_name}...")

        if extract_archives(install_path) != 1:
            self.error.emit(f"Failed extracting {asset_name}")
            return False

        self.config[version_key] = latest_version

        save_config(self.config)

        self._log(f"Updated to {latest_version}")

        return True
