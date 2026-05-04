"""Per-session logging to ~/.benchbox/logs/<timestamp>/session.log."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from rich.logging import RichHandler

DEFAULT_LOG_ROOT: Path = Path.home() / ".benchbox" / "logs"
ENV_LOG_DIR: str = "BENCHBOX_LOG_DIR"

_session_dir: Path | None = None


def _log_root() -> Path:
    override = os.environ.get(ENV_LOG_DIR)
    return Path(override) if override else DEFAULT_LOG_ROOT


def current_session_dir() -> Path | None:
    return _session_dir


def init_session(level: int = logging.INFO, log_root: Path | None = None) -> Path:
    global _session_dir
    if _session_dir is not None:
        return _session_dir

    root = log_root if log_root is not None else _log_root()
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    session = root / timestamp
    session.mkdir(parents=True, exist_ok=True)

    file_handler = logging.FileHandler(session / "session.log", encoding="utf-8")
    file_handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)-7s [%(name)s] %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    # File handler always captures DEBUG; console is curated by `level`.
    file_handler.setLevel(logging.DEBUG)
    console_handler = RichHandler(
        rich_tracebacks=True,
        show_time=False,
        show_path=False,
        markup=False,
    )
    console_handler.setLevel(level)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    _session_dir = session
    return session


def get_logger(name: str) -> logging.Logger:
    if _session_dir is None:
        init_session()
    return logging.getLogger(name)


def reset_for_testing() -> None:
    global _session_dir
    _session_dir = None
    root_logger = logging.getLogger()
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
        handler.close()
