import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config import get_app_dir

def setup_logger() -> logging.Logger:
    logger_current = logging.getLogger("xenia_manager")

    if logger_current.handlers:
        return logger_current

    logger_current.setLevel(logging.DEBUG)

    log_dir = get_app_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / "xbox_game_manager.log"

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    # File logging
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger_current.addHandler(file_handler)

    # Console logging
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger_current.addHandler(console_handler)

    return logger_current


logger = setup_logger()