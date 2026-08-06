"""Shared logging for Rock RMS scripts.

Logs to the Rock runtime directory with rotation (see rock_paths).
- INFO: short success lines (one per API call or command)
- ERROR: full context with stack traces
"""

import logging
from logging.handlers import RotatingFileHandler
import rock_paths

rock_paths.ensure()
LOG_PATH = rock_paths.LOG


def get_logger(name="rock"):
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    fh = RotatingFileHandler(LOG_PATH, maxBytes=2 * 1024 * 1024, backupCount=3)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(fh)

    return logger
