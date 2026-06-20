import json
import os
import sys

def get_app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)  # ✔ correct for frozen apps
    return os.path.dirname(os.path.abspath(__file__))

def load_config():
    datadir = get_app_dir()
    config_dir = os.path.join(datadir, "config")
    config_file = os.path.join(config_dir, ".x360-game-manager-config.json")
    print(config_dir)
    print(config_file)
    try:
        with open(config_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print("Config load error:", e)
        return {}


def save_config(data: dict):
    datadir = get_app_dir()
    config_dir = os.path.join(datadir, "config")
    config_file = os.path.join(config_dir, ".x360-game-manager-config.json")
    print(config_dir)
    print(config_file)
    try:
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print("Config save error:", e)