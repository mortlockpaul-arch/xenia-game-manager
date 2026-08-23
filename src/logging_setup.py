import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config import get_app_dir

def setup_logger() -> logging.Logger:
    logger = logging.getLogger("xenia_manager")

    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    log_dir = get_app_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / "xenia_manager.log"

    handler = RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger


logger = setup_logger()