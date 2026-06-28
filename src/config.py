import json
import os
from pathlib import Path

import sys

def get_app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)  # ✔ correct for frozen apps
    return os.path.dirname(os.path.abspath(__file__))

def load_xenia_manager_config(xenia_manager_path):
    xenia_manager_config_path = Path.joinpath(xenia_manager_path,"config")
    xenia_manager_config = os.path.join(xenia_manager_config_path,"config.json")
    try:
        with open(xenia_manager_config, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print("Config load error:", e)
        return {}

def load_config():
    datadir = get_app_dir()
    config_dir = os.path.join(datadir, "config")
    config_file = os.path.join(config_dir, ".x360-game-manager-config.json")
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