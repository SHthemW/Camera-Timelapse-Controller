from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from camera_timelapse.capture.common import next_group_number
from camera_timelapse.core.schedule import (
    has_reached_scheduled_time,
    parse_end_time,
    parse_start_time,
    wait_until_start_time,
)
from camera_timelapse.core.log import log
from camera_timelapse.cli_flow import (
    maybe_prompt_round_count,
    resolve_output_dir,
    run_dry_run_session,
    run_standard_session,
    validate_args,
)
from camera_timelapse.gphoto import GPhotoError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture +1 EV, 0 EV, and -1 EV photos through gPhoto2."
    )
    parser.add_argument(
        "output_dir",
        nargs="?",
        type=Path,
        help="Download directory. Example: .",
    )
    parser.add_argument(
        "--output-dir",
        dest="output_dir_flag",
        type=Path,
        help="Download directory. Use this instead of the positional path if preferred.",
    )
    parser.add_argument(
        "--mode",
        choices=("aeb", "manual"),
        default="aeb",
        help="Capture mode. Defaults to camera AEB; use manual for per-shot EV changes.",
    )
    parser.add_argument(
        "--config",
        help="Manual mode exposure compensation config path, if auto-detection fails.",
    )
    parser.add_argument(
        "--gphoto",
        default=shutil.which("gphoto2") or "gphoto2",
        help="Path to the gphoto2 executable.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print gPhoto2 commands without talking to a camera.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        help=(
            "Seconds between capture round starts. Time spent capturing and downloading "
            "counts toward the interval. Use 0 for no delay."
        ),
    )
    parser.add_argument(
        "--start-at",
        type=parse_start_time,
        metavar="HH:MM",
        help=(
            "Wait until today's 24-hour HH:MM time before starting capture. "
            "Omit to start immediately."
        ),
    )
    parser.add_argument(
        "--end-at",
        type=parse_end_time,
        metavar="HH:MM",
        help=(
            "Stop after the current group once today's 24-hour HH:MM time is reached. "
            "Omit to run until other limits stop the session."
        ),
    )
    parser.add_argument(
        "--round",
        dest="round_count",
        type=int,
        help="Total number of capture rounds. Omit to keep capturing forever.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    validate_args(parser, args)
    args.round_count = maybe_prompt_round_count(args.round_count)

    effective_end_at = None if args.round_count is not None else args.end_at
    if effective_end_at is not None and has_reached_scheduled_time(effective_end_at):
        log(
            f"Scheduled end time {effective_end_at:%H:%M} has already passed; stopping without capture",
            level="warn",
            file=sys.stderr,
        )
        return 0

    output_dir = resolve_output_dir(parser, args)

    try:
        wait_until_start_time(args.start_at)
    except KeyboardInterrupt:
        log("Interrupted by user", level="warn", file=sys.stderr)
        return 130

    if effective_end_at is not None and has_reached_scheduled_time(effective_end_at):
        log(
            f"Scheduled end time {effective_end_at:%H:%M} has already passed; stopping without capture",
            level="warn",
            file=sys.stderr,
        )
        return 0

    if not args.dry_run and shutil.which(args.gphoto) is None and not Path(args.gphoto).exists():
        log(
            "gphoto2 was not found. Install gPhoto2 and make sure it is available in PATH, "
            "or pass --gphoto /path/to/gphoto2.",
            level="error",
            file=sys.stderr,
        )
        return 127

    output_dir.mkdir(parents=True, exist_ok=True)
    start_group = next_group_number(output_dir)

    try:
        if args.dry_run:
            run_dry_run_session(args, output_dir, start_group, effective_end_at)
        else:
            run_standard_session(args, output_dir, start_group, effective_end_at)
    except KeyboardInterrupt:
        log("Interrupted by user", level="warn", file=sys.stderr)
        return 130
    except GPhotoError as exc:
        log(str(exc), level="error", file=sys.stderr)
        return 1

    log(f"Done. Files downloaded to: {output_dir.resolve()}")
    return 0
