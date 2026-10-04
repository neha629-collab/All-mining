"""
Professional Logger v2.0
- Console + rotating file
- Structured, safe for asyncio
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import config as cfg

def setup_logger(name: str = "bot") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # already configured

    level = getattr(logging, cfg.LOG_LEVEL, logging.INFO)
    logger.setLevel(level)

    fmt = logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(level)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # File
    if cfg.LOG_TO_FILE:
        log_file = cfg.LOGS_DIR / "bot.log"
        fh = RotatingFileHandler(
            log_file,
            maxBytes=cfg.LOG_MAX_BYTES,
            backupCount=cfg.LOG_BACKUP_COUNT,
            encoding="utf-8"
        )
        fh.setLevel(level)
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    # Reduce noise from libs
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)

    return logger

# Global loggers
bot_log = setup_logger("bot")
api_log = setup_logger("api")
sched_log = setup_logger("scheduler")
proxy_log = setup_logger("proxy")
