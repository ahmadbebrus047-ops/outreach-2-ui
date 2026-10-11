"""Uniform logging across all scripts and cron jobs."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from core import config


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:  # already configured
        return logger

    logger.setLevel(logging.INFO)
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
    )

    file_handler = RotatingFileHandler(
        config.LOG_DIR / f"{name}.log", maxBytes=2_000_000, backupCount=3
    )
    file_handler.setFormatter(fmt)

    console = logging.StreamHandler()
    console.setFormatter(fmt)

    logger.addHandler(file_handler)
    logger.addHandler(console)
    return logger
