import shutil
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import urlparse

import requests


class XeniaManagerInstaller:

    GITHUB_API = "https://api.github.com/repos/xenia-manager/xenia-manager/releases/latest"
    INSTALL_PATH = Path(r"C:\xenia-manager")
    MANAGER_OR_EDGE = "Manager"

    def install(self, log_callback=None):

        def log(msg):
            if log_callback:
                log_callback(msg)

        log(f"Checking for latest Xenia {self.MANAGER_OR_EDGE}...")

        release = requests.get(self.GITHUB_API, timeout=30)
        release.raise_for_status()
        data = release.json()
        asset = next(
            (
                a for a in data["assets"]
                if a["name"].lower().endswith(".zip")
            ),
            None,
        )

        if asset is None:
            raise RuntimeError("No ZIP release found.")

        url = asset["browser_download_url"]
        filename = Path(urlparse(url).path).name
        zip_path = Path(tempfile.gettempdir()) / filename

        log(f"Downloading {filename}...")

        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(zip_path, "wb") as f:
                for chunk in r.iter_content(1024 * 1024):
                    if chunk:
                        f.write(chunk)

        log("Extracting...")

        if self.INSTALL_PATH.exists():
            shutil.rmtree(self.INSTALL_PATH)

        self.INSTALL_PATH.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path) as z:
            z.extractall(self.INSTALL_PATH)

        log(f"Xenia {self.MANAGER_OR_EDGE} installed.")

        return self.INSTALL_PATH