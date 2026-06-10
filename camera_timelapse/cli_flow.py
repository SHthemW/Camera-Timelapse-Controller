from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

from camera_timelapse.camera.config import (
    find_exposure_config,
    read_aeb_current_index,
    shots_needed_to_finish_aeb_round,
)
from camera_timelapse.capture.aeb import (
    capture_aeb_round,
    download_aeb_rounds,
)
from camera_timelapse.capture.manual import (
    capture_manual_round,
    download_manual_rounds,
)
from camera_timelapse.capture.timing import (
    current_interval_timestamp,
    wait_for_next_round,
)
from camera_timelapse.core.constants import AEB_SHOT_COUNT
from camera_timelapse.core.log import log
from camera_timelapse.core.schedule import has_reached_scheduled_time
from camera_timelapse.gphoto import GPhotoError, run_gphoto
from camera_timelapse.parsing import parse_choices
from camera_timelapse.system.ptpcamera_guard import suppress_ptpcamerad
from camera_timelapse.capture.session import run_capture_and_download_session


def validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.interval is not None and args.interval < 0:
        parser.error("--interval must be 0 or a positive number of seconds.")
    if args.round_count is not None and args.round_count <= 0:
        parser.error("--round must be a positive integer.")
    if args.round_count is not None and args.end_at is not None:
        log("--round was provided, so --end-at will be ignored.", level="warn", file=sys.stderr)


def resolve_output_dir(parser: argparse.ArgumentParser, args: argparse.Namespace) -> Path:
    positional_output_dir = getattr(args, "output_dir", None)
    flag_output_dir = getattr(args, "output_dir_flag", None)

    if positional_output_dir is not None and flag_output_dir is not None:
        if positional_output_dir.resolve() != flag_output_dir.resolve():
            parser.error("Provide output directory either positionally or with --output-dir, not both.")
        return flag_output_dir.resolve()

    if flag_output_dir is not None:
        return flag_output_dir.resolve()

    if positional_output_dir is not None:
        return positional_output_dir.resolve()

    if not sys.stdin.isatty():
        parser.error("Output directory is required. Pass one positionally or run interactively to be prompted.")

    while True:
        answer = input("请输入输出目录（例如 .）: ").strip()
        if not answer:
            print("请输入有效的输出目录。")
            continue
        return Path(answer).expanduser().resolve()


def maybe_prompt_round_count(round_count: int | None, end_at: dt.time | None) -> int | None:
    if round_count is not None:
        return round_count
    if end_at is not None:
        return None

    log("未提供 --round，程序将持续循环拍摄。", level="warn", file=sys.stderr)
    if not sys.stdin.isatty():
        log("当前输入不是交互式终端，无法补充参数，继续循环拍摄。", level="warn", file=sys.stderr)
        return None

    answer = input("是否要现在补充 --round 参数？[y/N] ").strip().lower()
    if answer not in {"y", "yes"}:
        return None

    while True:
        raw_round_count = input("请输入总拍摄轮数: ").strip()
        try:
            value = int(raw_round_count)
        except ValueError:
            print("请输入正整数。")
            continue
        if value <= 0:
            print("请输入正整数。")
            continue
        return value


def prepare_manual_context(args: argparse.Namespace) -> tuple[str, list[str]]:
    exposure_config = find_exposure_config(args.gphoto, args.config, dry_run=args.dry_run)
    log(f"Using exposure compensation config: {exposure_config}")
    config_output = run_gphoto(args.gphoto, ["--get-config", exposure_config], dry_run=args.dry_run)
    choices = parse_choices(config_output)
    return exposure_config, choices


def capture_single_round(
    args: argparse.Namespace,
    exposure_config: str | None,
    choices: list[str] | None,
) -> list[tuple[str, str]] | list[tuple[int, str, str]]:
    if args.mode == "aeb":
        current_index = read_aeb_current_index(args.gphoto, dry_run=args.dry_run)
        shots_to_take = shots_needed_to_finish_aeb_round(current_index)
        if current_index > 1:
            log(
                f"Continuing partial AEB round from shot {current_index}/{AEB_SHOT_COUNT}; "
                f"{shots_to_take} shot(s) needed to finish"
            )
        else:
            log("Starting a fresh AEB round")
        return capture_aeb_round(
            args.gphoto,
            shots_to_take,
            dry_run=args.dry_run,
        )

    if exposure_config is None or choices is None:
        raise GPhotoError("Manual mode exposure configuration was not prepared.")

    return capture_manual_round(
        args.gphoto,
        exposure_config,
        choices,
        dry_run=args.dry_run,
    )


def run_dry_run_session(
    args: argparse.Namespace,
    output_dir: Path,
    start_group: int,
    end_at: dt.time | None,
) -> None:
    with suppress_ptpcamerad():
        exposure_config: str | None = None
        choices: list[str] | None = None
        if args.mode == "manual":
            exposure_config, choices = prepare_manual_context(args)
            if end_at is not None and has_reached_scheduled_time(end_at):
                log(
                    f"Scheduled end time {end_at:%H:%M} has already passed; stopping without capture",
                    level="warn",
                    file=sys.stderr,
                )
                return

        completed_rounds = 0
        while args.round_count is None or completed_rounds < args.round_count:
            round_started_at = current_interval_timestamp()
            round_number = start_group + completed_rounds
            log(f"Starting capture round {round_number:04d}")
            captured_rounds = [capture_single_round(args, exposure_config, choices)]
            if args.mode == "aeb":
                download_aeb_rounds(
                    args.gphoto,
                    output_dir,
                    round_number,
                    captured_rounds,  # type: ignore[arg-type]
                    dry_run=True,
                )
            else:
                download_manual_rounds(
                    args.gphoto,
                    output_dir,
                    round_number,
                    captured_rounds,  # type: ignore[arg-type]
                    dry_run=True,
                )
            completed_rounds += 1

            if args.round_count is not None and completed_rounds >= args.round_count:
                break

            if end_at is not None and has_reached_scheduled_time(end_at):
                log(f"Scheduled end time {end_at:%H:%M} reached; stopping after this round")
                break

            wait_for_next_round(round_started_at, args.interval)


def run_standard_session(
    args: argparse.Namespace,
    output_dir: Path,
    start_group: int,
    end_at: dt.time | None,
) -> None:
    with suppress_ptpcamerad():
        exposure_config: str | None = None
        choices: list[str] | None = None
        if args.mode == "manual":
            exposure_config, choices = prepare_manual_context(args)
            if end_at is not None and has_reached_scheduled_time(end_at):
                log(
                    f"Scheduled end time {end_at:%H:%M} has already passed; stopping without capture",
                    level="warn",
                    file=sys.stderr,
                )
                return
        run_capture_and_download_session(
            gphoto=args.gphoto,
            output_dir=output_dir,
            start_group=start_group,
            total_rounds=args.round_count,
            interval=args.interval,
            mode=args.mode,
            exposure_config=exposure_config,
            choices=choices,
            end_at=end_at,
        )
