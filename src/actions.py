import os
from pathlib import Path
import requests

from config import load_config
from extract import extract_archives


class DownloadArtifact:
    OWNER = "AdrianCassar"
    REPO = "xenia-canary"

    def __init__(self, token=None, log_callback=None):
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })

        self.log = log_callback or (lambda x: None)

        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"

    def latest_artifact(self, name_contains="windows"):
        r = self.session.get(
            f"https://api.github.com/repos/{self.OWNER}/{self.REPO}/actions/runs",
            params={
                "status": "success",
                "per_page": 1,
            },
        )
        r.raise_for_status()

        run = r.json()["workflow_runs"][0]
        run_id = run["id"]

        self.log(f"Latest run: {run_id}")

        r = self.session.get(
            f"https://api.github.com/repos/{self.OWNER}/{self.REPO}/actions/runs/{run_id}/artifacts"
        )
        r.raise_for_status()

        artifacts = r.json()["artifacts"]

        for artifact in artifacts:
            if name_contains.lower() in artifact["name"].lower():
                return artifact, run

        raise RuntimeError(f"No artifact containing '{name_contains}' found.")

    def download(self, output_dir="."):
        artifact, run = self.latest_artifact()

        version = f"build-{run['run_number']}"

        self.log(f"Downloading: {artifact['name']}")

        r = self.session.get(
            artifact["archive_download_url"],
            allow_redirects=True,
            stream=True,
        )
        r.raise_for_status()

        path = Path(output_dir) / f"{artifact['name']}.zip"

        with open(path, "wb") as f:
            for chunk in r.iter_content(8192):
                if chunk:
                    f.write(chunk)

        self.log(f"Downloaded: {path}")

        return {
            "path": path,
            "version": f"build-{run['run_number']}",
            "artifact": artifact["name"],
            "sha": run["head_sha"][:7],
            "build_date": run["created_at"]
        }
