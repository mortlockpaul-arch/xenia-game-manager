import json
import os
import subprocess
from pathlib import Path
from typing import cast, Any
from urllib.parse import urlparse

import requests
from PySide6.QtCore import QObject, Signal, QThread
from PySide6.QtWidgets import QWidget
from packaging.version import Version, InvalidVersion
from requests import Timeout, Session
from requests.exceptions import HTTPError, RequestException

from config import load_config, save_config, get_app_dir
from extract import extract_archives


class UpdateWorker(QThread):

    log = Signal(str)
    progress = Signal(int, int)
    update_finished = Signal()
    error = Signal(str)
    show_message = Signal(str, str)
    quit_app = Signal()

    def __init__(self, name, parent=None):
        super().__init__(parent)
        self.name = name
        self.updater = None

    def run(self):

        self.updater = UpdateManager(self)
        self.updater.show_message.connect(
            self.show_message
        )
        self.updater.log.connect(self.log)
        self.updater.progress.connect(self.progress)
        self.updater.finished.connect(self.update_finished)
        self.updater.error.connect(self.error)
        self.updater.quit_app.connect(self.quit_app.emit)
        try:
            self.updater.check_for_updates(name=self.name)

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
    show_message = Signal(str, str)  # title, message
    quit_app = Signal()

    def __init__(self, parent):
        super().__init__(parent)
        self.session = Session()
        self.session.headers.update({
            "Accept": "application/vnd.github+json",
        })
        self.config = load_config()
        self.parent = parent

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


    def check_for_github_update(
            self,
            url,
            current_version,
            asset_index=0,
            asset_match=None,
    ):
        """
        Checks GitHub for a newer release.

        Returns:
            (latest_version, download_url) if an update is available,
            otherwise None.
        """
        response = self.session.get(url, timeout=30)
        try:
            response.raise_for_status()
        except Timeout as e:
            raise RuntimeError("GitHub request timed out.") from e
        except ConnectionError as e:
            raise RuntimeError("Unable to connect to GitHub.") from e
        except HTTPError as e:
            raise RuntimeError(
                f"GitHub returned HTTP {response.status_code}."
            ) from e
        except RequestException as e:
            raise RuntimeError(
                f"GitHub request failed: {e}"
            ) from e

        release = response.json()

        latest_version = release["tag_name"].lstrip("v")
        current_version = str(current_version).lstrip("v")

        try:
            update_available = Version(latest_version) > Version(current_version)
        except InvalidVersion:
            # Current version isn't semantic (e.g. Git SHA)
            update_available = latest_version != current_version

        if not update_available:
            return None

        assets = release.get("assets", [])

        if not assets:
            return None

        # Select asset by filename if requested
        if asset_match:
            asset = next((a for a in assets if asset_match.lower() in a["name"].lower()), None,)
            if asset is None:
                raise RuntimeError(f"No asset matching '{asset_match}' found.")
        else:
            if asset_index >= len(assets):
                raise RuntimeError(f"Release only contains {len(assets)} asset(s).")
            asset = assets[asset_index]
        asset = cast(dict[str, Any], asset)
        return latest_version, asset["browser_download_url"]

    def check_for_updates(self, name="Xenia Edge"):

        if name == "Xenia Edge": self._check_component(
            name="Xenia Edge",
            version_key="xenia_edge_version",
            install_path=self.config["xenia_edge_path"],
            current_version=self.config["xenia_edge_version"],
            github_url=self.config["xenia_edge_url"],
            asset_index=2,
        )

        if name == "Xenia Game Manager": self._check_component(
            name="Xenia Game Manager",
            version_key="game_manager_version",
            install_path=self.config["xenia_game_manager_portable_path"],
            current_version=self.config["game_manager_version"],
            github_url=self.config["xenia_game_manager_url"],
        )

        self.finished.emit()

    def _check_component(
            self,
            name,
            version_key,
            install_path,
            current_version,
            github_url,
            asset_index=0,
            asset_name=None,
    ):

        asset_match:str = ""

        if name == "Xenia Game Manager":
            if Path(get_app_dir() / "portable.txt").exists():
                asset_match = "portable"
            else:
                asset_match = ".msi"
        # if name == "Xenia Edge":
            edge_path = Path(self.config["xenia_edge_path"])
            # if Path(edge_path / "portable.txt").exists():
            #     asset_match = "portable"
            # else:
            #     asset_match = ".msi"

        result = self.check_for_github_update(
            url=github_url,
            current_version=current_version,
            asset_index=asset_index,
            asset_match=asset_match,
        )

        if not result:
            if name == "Xenia Game Manager":
                self._log(f"No {name} {asset_match} update available")
            if name == "Xenia Edge":
                self._log(f"No {name} {asset_match} update available")
            return False

        latest_version, asset_url = result

        if asset_name is None:
            asset_name = Path(
                urlparse(asset_url).path
            ).name

        self._log(f"{name} Update found: {current_version} -> {latest_version}")

        if asset_match != "portable":
            asset_path = Path.home() / "downloads" / asset_name
        else:
            asset_path = (Path(install_path) / asset_name)

        try:
            self.download_file(asset_url, asset_path, archive_org=False,)

        except requests.RequestException as e:
            self.error.emit(f"Download failed: {e}")
            return False

        self.config[version_key] = latest_version
        save_config(self.config)

        if name == "Xenia Edge":
            if asset_path.suffix.lower() in {".zip", ".7z"}:
                self._log(f"Extracting {asset_name}...")
                if extract_archives(asset_path.parent) != 1:
                    self.error.emit(f"Failed extracting {asset_name}")
                    return False
                self.show_message.emit(
                    "Update Ready",
                    f"Installing {asset_name}..."
                )
        if name == "Xenia Game Manager":
            updater_path = get_app_dir() / "Xenia Game Manager Updater.exe"
            if asset_path.suffix.lower() in {".zip", ".7z"}:
                self._log(f"Extracting {asset_name}...")
                if extract_archives(asset_path.parent) != 1:
                    self.error.emit(f"Failed extracting {asset_name}")
                    return False
                zip_path = asset_path.parent
                install_dir = updater_path.parent
                self.show_message.emit(
                    "Update Ready",
                    f"Installing {asset_name}..."
                )
                # msg = QMessageBox()
                # msg.setIcon(QMessageBox.Icon.Information)
                # msg.setWindowTitle("Update Ready")
                # msg.setText(f"Installing {asset_name}...")
                # msg.exec()
                subprocess.Popen(
                    [
                        str(updater_path),
                        "--zip",
                        str(zip_path),
                        "--target",
                        str(install_dir),
                        "--pid",
                        str(os.getpid()),
                    ],
                    creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                    close_fds=True,
                )

                self.quit_app.emit()

            if asset_path.suffix.lower() in {".msi", ".exe"}:
                parent = cast(QWidget, self.parent)
                self.show_message.emit(
                    "Update Ready",
                    f"Installing {asset_name}..."
                )
                # msg = QMessageBox()
                # msg.setIcon(QMessageBox.Icon.Information)
                # msg.setWindowTitle("Update Ready")
                # msg.setText(f"Installing {asset_name}...")
                # msg.exec()
                subprocess.Popen([
                    "msiexec",
                    "/i",
                    asset_path,
                ],
                    creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                    close_fds=True,)
                self.quit_app.emit()


        self._log(f"{name} Updated to {latest_version}")

        return True
