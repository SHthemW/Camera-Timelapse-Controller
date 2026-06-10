from __future__ import annotations

import datetime as dt
import sys


def current_timestamp() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(message: str, *, file=None) -> None:
    if file is None:
        file = sys.stdout
    print(f"[{current_timestamp()}] {message}", file=file)

