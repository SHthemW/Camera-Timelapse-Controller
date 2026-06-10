from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

from .camera.config import find_exposure_config
from .capture import capture_aeb_bracket, capture_bracket
from .gphoto import GPhotoError
from .core.log import log
from .system.ptpcamera_guard import suppress_ptpcamerad


def build_parser() -> argparse.ArgumentParser:
    script_dir = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Capture +1 EV, 0 EV, and -1 EV photos through gPhoto2."
    )
    parser.add_argument(
        "--mode",
        choices=("aeb", "manual"),
        default="aeb",
        help="Capture mode. Defaults to camera AEB; use manual for per-shot EV changes.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=script_dir / "capture",
        help="Download directory. Defaults to ./capture next to this script.",
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
            "Seconds to wait after each group before automatically capturing the next group. "
            "Use 0 for no delay. Omit to capture one group only."
        ),
    )
    return parser


def validate_interval(parser: argparse.ArgumentParser, interval: float | None) -> None:
    if interval is not None and interval < 0:
        parser.error("--interval must be 0 or a positive number of seconds.")


def capture_one_group(args: argparse.Namespace) -> None:
    if args.mode == "aeb":
        log("Using camera AEB mode")
        capture_aeb_bracket(
            args.gphoto,
            args.output_dir.resolve(),
            dry_run=args.dry_run,
        )
    else:
        exposure_config = find_exposure_config(args.gphoto, args.config, dry_run=args.dry_run)
        log(f"Using exposure compensation config: {exposure_config}")
        capture_bracket(
            args.gphoto,
            args.output_dir.resolve(),
            exposure_config,
            dry_run=args.dry_run,
        )


def capture_with_optional_interval(args: argparse.Namespace) -> None:
    if args.interval is None:
        capture_one_group(args)
        return

    group_count = 0
    log(f"Interval capture enabled; next group starts after {args.interval:g} second(s)")

    while True:
        group_count += 1
        log(f"Starting interval capture cycle {group_count}")
        capture_one_group(args)

        if args.interval > 0:
            log(f"Waiting {args.interval:g} second(s) before next group")
            time.sleep(args.interval)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    validate_interval(parser, args.interval)

    if not args.dry_run and shutil.which(args.gphoto) is None and not Path(args.gphoto).exists():
        log(
            "gphoto2 was not found. Install gPhoto2 and make sure it is available in PATH, "
            "or pass --gphoto /path/to/gphoto2.",
            file=sys.stderr,
        )
        return 127

    try:
        with suppress_ptpcamerad():
            capture_with_optional_interval(args)
    except KeyboardInterrupt:
        log("Interrupted by user", file=sys.stderr)
        return 130
    except GPhotoError as exc:
        log(str(exc), file=sys.stderr)
        return 1

    log(f"Done. Files downloaded to: {args.output_dir.resolve()}")
    return 0
