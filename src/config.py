import os
import json
from pathlib import Path

CONFIG_FILE = os.path.expanduser("~/.x360-game-manager-config.json")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(BASE_DIR, "config")
XENIA_EXE = r"D:\RetroBat\emulators\xenia-manager\Emulators\Xenia Canary\xenia_canary.exe"
GAMES_JSON = r"D:\RetroBat\emulators\xenia-manager\Config\games.json"
XENIA_BASE_DIR = Path(    r"D:\RetroBat\emulators\xenia-manager")

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {}

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(data: dict):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print("Config save error:", e)