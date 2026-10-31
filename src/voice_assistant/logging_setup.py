from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

from voice_assistant.config import Settings


class UTCFormatter(logging.Formatter):
    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def new_turn_id() -> str:
    return uuid.uuid4().hex[:12]


def setup_logging(settings: Settings) -> logging.Logger:
    logger = logging.getLogger("voice_assistant")
    logger.setLevel(settings.log_level.upper())
    logger.handlers.clear()
    logger.propagate = False

    formatter = UTCFormatter("%(asctime)s turn=%(turn_id)s %(levelname)s %(name)s %(message)s")

    class _TurnIdFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            if not hasattr(record, "turn_id"):
                record.turn_id = "-"
            return True

    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    stream.addFilter(_TurnIdFilter())
    logger.addHandler(stream)

    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    file_handler = RotatingFileHandler(
        log_dir / "assistant.log",
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(_TurnIdFilter())
    logger.addHandler(file_handler)
    return logger


class TurnLogger(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        extra = kwargs.setdefault("extra", {})
        extra.setdefault("turn_id", self.extra.get("turn_id", "-"))
        return msg, kwargs
