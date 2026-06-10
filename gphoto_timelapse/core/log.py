from __future__ import annotations

import datetime as dt
import sys
from typing import TextIO


LOG_COLORS = {
    "debug": "\033[2m",
    "info": "",
    "warn": "\033[33m",
    "error": "\033[31m",
}
LOG_LEVEL_LABELS = {
    "debug": "D",
    "info": "I",
    "warn": "W",
    "error": "E",
}
RESET_COLOR = "\033[0m"


def current_timestamp() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def current_log_time() -> str:
    return dt.datetime.now().strftime("%H:%M:%S")


def log(message: str, *, level: str = "info", file: TextIO | None = None) -> None:
    normalized_level = level.lower()
    if normalized_level not in LOG_COLORS:
        raise ValueError(f"Unknown log level: {level}")

    if file is None:
        file = sys.stderr if normalized_level == "error" else sys.stdout

    line = f"[{current_log_time()} {LOG_LEVEL_LABELS[normalized_level]}] {message}"
    color = LOG_COLORS[normalized_level]
    if color and file.isatty():
        line = f"{color}{line}{RESET_COLOR}"

    print(line, file=file)
