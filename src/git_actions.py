import errno

import time
from pathlib import Path

import requests


class DownloadArtifact:
    OWNER = "AdrianCassar"
    REPO = "xenia-canary"

    def check_token(self):
        if not self.token:
            return False, "No GitHub token configured"

        try:
            response = self.session.get(
                "https://api.github.com/user",
                timeout=10,
            )

            if response.status_code == 200:
                user = response.json()
                return True, f"Authenticated as {user.get('login', 'unknown')}"

            if response.status_code == 401:
                return False, "GitHub token is invalid or expired"

            return False, (
                f"GitHub authentication check failed: "
                f"HTTP {response.status_code}"
            )

        except requests.RequestException as e:
            return False, f"Unable to contact GitHub: {e}"

    def __init__(self, token=None, log_callback=None):
        self.token = token
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })

        self.log = log_callback or (lambda x: None)

        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"


    def latest_artifact(self, name_contains="windows"):
        url = f"https://api.github.com/repos/{self.OWNER}/{self.REPO}/actions/runs"
        for attempt in range(3):
            r = self.session.get(
                url,
                params={"status": "success", "per_page": 1},
                headers=self.session.headers,
                timeout=15,
            )

            if r.status_code == 503:
                print(f"GitHub unavailable, retrying ({attempt + 1}/3)...")
                time.sleep(2)
                continue

            r.raise_for_status()
            break
        else:
            raise RuntimeError("GitHub API is unavailable after 3 attempts.")

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

        try:
            r = self.session.get(
                artifact["archive_download_url"],
                allow_redirects=True,
                stream=True,
            )
            r.raise_for_status()
        except requests.exceptions.HTTPError as e:
            self.log(f"Error downloading artifact: {e}")
            return {}


        path = Path(output_dir) / f"{artifact['name']}.zip"

        try:
            with open(path, "wb") as f:
                for chunk in r.iter_content(8192):
                    if chunk:
                        f.write(chunk)
        except OSError as e:
            raise
        except Exception as e:
            raise

        self.log(f"Downloaded: {path}")

        return {
            "path": path,
            "version": f"build-{run['run_number']}",
            "artifact": artifact["name"],
            "sha": run["head_sha"][:7],
            "build_date": run["created_at"]
        }
