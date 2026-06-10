from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
import time

from camera_timelapse.core.log import log


START_TIME_PATTERN = re.compile(r"^\d{2}:\d{2}$")


def parse_hhmm(value: str, flag_name: str) -> dt.time:
    if not START_TIME_PATTERN.fullmatch(value):
        raise argparse.ArgumentTypeError(f"{flag_name} must use 24-hour HH:MM format.")

    hour_text, minute_text = value.split(":", maxsplit=1)
    hour = int(hour_text)
    minute = int(minute_text)
    if hour > 23 or minute > 59:
        raise argparse.ArgumentTypeError(f"{flag_name} must use a valid 24-hour HH:MM time.")

    return dt.time(hour=hour, minute=minute)


def parse_start_time(value: str) -> dt.time:
    return parse_hhmm(value, "--start-at")


def parse_end_time(value: str) -> dt.time:
    return parse_hhmm(value, "--end-at")


def scheduled_datetime_today(start_time: dt.time, now: dt.datetime | None = None) -> dt.datetime:
    if now is None:
        now = dt.datetime.now()

    return dt.datetime.combine(now.date(), start_time)


def has_reached_scheduled_time(scheduled_time: dt.time, now: dt.datetime | None = None) -> bool:
    if now is None:
        now = dt.datetime.now()

    return now >= scheduled_datetime_today(scheduled_time, now)


def wait_until_start_time(start_time: dt.time | None) -> None:
    if start_time is None:
        return

    now = dt.datetime.now()
    scheduled_at = scheduled_datetime_today(start_time, now)
    delay = (scheduled_at - now).total_seconds()
    if delay <= 0:
        log(
            f"Scheduled start time {scheduled_at:%Y-%m-%d %H:%M} has already passed; "
            "starting immediately",
            level="warn",
            file=sys.stderr,
        )
        return

    log(f"Scheduled start at {scheduled_at:%Y-%m-%d %H:%M}; waiting {delay:.0f} second(s)")
    time.sleep(delay)
