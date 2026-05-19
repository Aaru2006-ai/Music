"""
Logging configuration — structured, coloured, with file rotation.
"""

import logging
import logging.handlers
import os
import sys
from datetime import datetime

LOG_DIR = os.path.join(os.path.dirname(__file__), "../../logs")
os.makedirs(LOG_DIR, exist_ok=True)


class _Formatter(logging.Formatter):
    GREY   = "\x1b[38;5;240m"
    CYAN   = "\x1b[36m"
    YELLOW = "\x1b[33m"
    RED    = "\x1b[31m"
    BOLD_RED = "\x1b[31;1m"
    RESET  = "\x1b[0m"

    FORMATS = {
        logging.DEBUG:    GREY    + "[%(levelname)-8s] %(name)s: %(message)s" + RESET,
        logging.INFO:     CYAN    + "[%(levelname)-8s] %(name)s: %(message)s" + RESET,
        logging.WARNING:  YELLOW  + "[%(levelname)-8s] %(name)s: %(message)s" + RESET,
        logging.ERROR:    RED     + "[%(levelname)-8s] %(name)s: %(message)s" + RESET,
        logging.CRITICAL: BOLD_RED + "[%(levelname)-8s] %(name)s: %(message)s" + RESET,
    }

    def format(self, record: logging.LogRecord) -> str:
        fmt = self.FORMATS.get(record.levelno, self.FORMATS[logging.DEBUG])
        formatter = logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S")
        return formatter.format(record)


def setup_logger(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    root.setLevel(level)

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(_Formatter())
    root.addHandler(ch)

    # Rotating file handler — 5 MB × 3 backups
    log_file = os.path.join(LOG_DIR, f"musicbot_{datetime.now().strftime('%Y%m%d')}.log")
    fh = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    fh.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    root.addHandler(fh)

    # Silence noisy third-party loggers
    for noisy in ("pyrogram", "pytgcalls", "motor", "aioredis", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    root.info("Logger initialised. File: %s", log_file)
  
