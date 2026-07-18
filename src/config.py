import json
import os
from pathlib import Path

import sys


def get_app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent  # Frozen executable directory
    return Path(__file__).resolve().parent  # Script directory


def load_xenia_manager_config():
    config = load_config()
    xenia_manager_path = Path(config["xenia_manager_path"])
    xenia_manager_config_path = Path.joinpath(xenia_manager_path, "config")
    xenia_manager_config = Path.joinpath(xenia_manager_config_path, "config.json")
    if not xenia_manager_config.exists():
        return {}, xenia_manager_path
    try:
        with open(xenia_manager_config, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        raise RuntimeError(f"Config Load Error: {e}") from e
    return config, xenia_manager_path

def load_config():
    datadir = get_app_dir()
    config_dir = os.path.join(datadir, "config")
    config_file = os.path.join(config_dir, "game-manager-config.json")
    try:
        with open(config_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise RuntimeError(f"Config Load Error: {e}") from e


def save_config(data: dict):
    datadir = get_app_dir()
    config_dir = os.path.join(datadir, "config")
    config_file = os.path.join(config_dir, "game-manager-config.json")
    try:
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        raise RuntimeError(f"Config Save Error: {e}") from e
