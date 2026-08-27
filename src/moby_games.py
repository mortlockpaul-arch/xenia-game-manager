from __future__ import annotations
import json
import time
from pathlib import Path
import requests

class MobyGamesClient:
    BASE_URL = "https://api.mobygames.com/v1"

    def __init__(
        self,
        api_key: str,
        cache_file: Path | None = None,
        min_request_interval: float = 1.0,
    ):
        self.api_key = api_key
        self.cache_file = cache_file
        self.min_request_interval = min_request_interval

        self._last_request = 0.0
        self._cache: dict[str, dict] = {}

        if cache_file and cache_file.exists():
            try:
                self._cache = json.loads(
                    cache_file.read_text(encoding="utf-8")
                )
            except (json.JSONDecodeError, OSError):
                self._cache = {}

    def _save_cache(self):
        if not self.cache_file:
            return

        self.cache_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.cache_file.write_text(
            json.dumps(
                self._cache,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def _request(self, endpoint: str, **params) -> dict:
        elapsed = time.monotonic() - self._last_request

        if elapsed < self.min_request_interval:
            time.sleep(
                self.min_request_interval - elapsed
            )

        params["api_key"] = self.api_key

        response = requests.get(
            f"{self.BASE_URL}/{endpoint.lstrip('/')}",
            params=params,
            timeout=30,
        )

        self._last_request = time.monotonic()

        response.raise_for_status()

        return response.json()

    @staticmethod
    def _normalise_title(title: str) -> str:
        return " ".join(
            title.casefold().strip().split()
        )

    def get_publisher(
        self,
        title: str,
    ) -> str | None:

        cache_key = self._normalise_title(title)

        cached = self._cache.get(cache_key)

        if cached is not None:
            return cached.get("publisher")

        try:
            data = self._request(
                "/games",
                title=title,
                format="normal",
            )
        except requests.RequestException:
            return None

        games = data.get("games", [])

        if not games:
            self._cache[cache_key] = {
                "publisher": None,
            }
            self._save_cache()
            return None

        # Prefer an exact title match.
        normalised = self._normalise_title(title)

        exact_matches = [
            game
            for game in games
            if self._normalise_title(
                game.get("title", "")
            ) == normalised
        ]

        game = (
            exact_matches[0]
            if exact_matches
            else games[0]
        )

        game_id = game.get("game_id")

        if not game_id:
            return None

        try:
            platforms = self._request(
                f"/games/{game_id}/platforms",
                format="normal",
            )
        except requests.RequestException:
            return None

        publisher = self._find_publisher(
            game_id,
            platforms,
        )

        self._cache[cache_key] = {
            "game_id": game_id,
            "publisher": publisher,
        }

        self._save_cache()

        return publisher

    def _find_publisher(
        self,
        game_id: int,
        platforms: dict,
    ) -> str | None:

        for platform in platforms.get("platforms", []):
            platform_id = platform.get("platform_id")

            if not platform_id:
                continue

            platform_name = (
                platform.get("platform_name", "")
                .casefold()
            )

            # XBLIG titles are generally represented
            # under Xbox 360 in MobyGames.
            if "xbox 360" not in platform_name:
                continue

            try:
                data = self._request(
                    f"/games/{game_id}/platforms/{platform_id}",
                    format="normal",
                )
            except requests.RequestException:
                continue

            for release in data.get("releases", []):
                companies = release.get(
                    "companies",
                    [],
                )

                # Prefer an explicit publisher.
                for company in companies:
                    if (
                        company.get("role", "")
                        .casefold()
                        == "published by"
                    ):
                        return company.get(
                            "company_name"
                        )

                # XBLIG developers are often also
                # the publisher.
                for company in companies:
                    if (
                        company.get("role", "")
                        .casefold()
                        == "developed by"
                    ):
                        return company.get(
                            "company_name"
                        )

        return None
