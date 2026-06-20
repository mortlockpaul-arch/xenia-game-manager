import os

from PySide6.QtCore import QThread, Signal

from xboxunity_api import (
    search_tus,
    download_tu
)


class TUDownloadWorker(QThread):
    log = Signal(str)
    progress = Signal(int, int)          # current, total
    game_progress = Signal(int, int)     # game index, total games
    finished = Signal(dict)

    def __init__(self, games, token=None, api_key=None, output_folder=""):
        super().__init__()
        self.games = games
        self.token = token
        self.api_key = api_key
        self.output_folder = output_folder

    def run(self):
        total_games = len(self.games)

        stats = {
            "games_total": total_games,
            "games_with_tu": 0,
            "tus_downloaded": 0,
            "errors": 0
        }

        self.log.emit("Starting TU download process...\n")

        for game_index, game in enumerate(self.games, 1):
            game_name = game.get("title")
            media_id = game.get("media_id")
            title_id = game.get("game_id")

            self.game_progress.emit(game_index, total_games)

            self.log.emit(f"Searching TUs for: {game_name}")

            try:
                tus = search_tus(
                    media_id=media_id,
                    title_id=title_id,
                    token=self.token,
                    api_key=self.api_key
                )
            except Exception as e:
                self.log.emit(f"ERROR searching TUs: {e}")
                stats["errors"] += 1
                continue

            if not tus:
                self.log.emit(f"No TUs found for {game_name}")
                continue

            stats["games_with_tu"] += 1

            game_folder = os.path.join(
                self.output_folder,
                self._safe_name(game_name)
            )
            os.makedirs(game_folder, exist_ok=True)

            self.log.emit(f"Found {len(tus)} TUs for {game_name}")

            for tu in tus:
                filename = tu.get("fileName")
                download_url = tu.get("downloadUrl")

                destination = os.path.join(game_folder, filename)

                self.log.emit(f"Downloading {filename}")

                try:
                    success, original_file = download_tu(
                        download_url,
                        destination,
                        progress_callback=self._progress_callback
                    )

                    if success:
                        stats["tus_downloaded"] += 1
                        self.log.emit(f"Downloaded: {filename}")
                    else:
                        stats["errors"] += 1
                        self.log.emit(f"FAILED: {filename}")

                except Exception as e:
                    stats["errors"] += 1
                    self.log.emit(f"ERROR downloading {filename}: {e}")

        self.log.emit("TU download completed.")
        self.finished.emit(stats)

    def _progress_callback(self, completed, total):
        if total > 0:
            self.progress.emit(completed, total)

    def _safe_name(self, name):
        import re
        name = re.sub(r'[<>:"/\\|?*]', "_", name)
        return name[:100].strip()
