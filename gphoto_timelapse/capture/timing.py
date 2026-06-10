from __future__ import annotations

import sys
import time

from gphoto_timelapse.core.log import log


def current_interval_timestamp() -> float:
    return time.monotonic()


def wait_for_next_round(round_started_at: float, interval: float | None) -> None:
    if interval is None or interval <= 0:
        return

    elapsed = current_interval_timestamp() - round_started_at
    remaining = interval - elapsed
    if remaining <= 0:
        log(
            f"Round elapsed {elapsed:.1f} second(s), exceeding interval {interval:g}; "
            "starting next round immediately",
            level="warn",
            file=sys.stderr,
        )
        return

    log(
        f"Waiting {remaining:.1f} second(s) before next round "
        f"(elapsed {elapsed:.1f}/{interval:g} second(s))"
    )
    time.sleep(remaining)
