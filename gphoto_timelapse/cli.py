from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

from gphoto_timelapse.camera.config import (
    find_exposure_config,
    latest_dcim_folder,
    read_aeb_current_index,
    read_aeb_current_index_in_shell,
    shots_needed_to_finish_aeb_round,
)
from gphoto_timelapse.capture.aeb import (
    capture_aeb_round,
    capture_aeb_round_in_shell,
    download_aeb_rounds,
)
from gphoto_timelapse.capture.common import next_group_number
from gphoto_timelapse.capture.manual import (
    capture_manual_round,
    capture_manual_round_in_shell,
    download_manual_rounds,
)
from gphoto_timelapse.core.constants import AEB_SHOT_COUNT
from gphoto_timelapse.core.log import log
from gphoto_timelapse.gphoto import GPhotoError, GPhotoShellSession, run_gphoto
from gphoto_timelapse.parsing import parse_choices
from gphoto_timelapse.system.ptpcamera_guard import suppress_ptpcamerad


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
            "Seconds to wait after each capture round before starting the next round. "
            "Use 0 for no delay."
        ),
    )
    parser.add_argument(
        "--round",
        dest="round_count",
        type=int,
        help="Total number of capture rounds. Omit to keep capturing forever.",
    )
    return parser


def validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.interval is not None and args.interval < 0:
        parser.error("--interval must be 0 or a positive number of seconds.")
    if args.round_count is not None and args.round_count <= 0:
        parser.error("--round must be a positive integer.")


def maybe_prompt_round_count(round_count: int | None) -> int | None:
    if round_count is not None:
        return round_count

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


def capture_single_round_in_shell(
    args: argparse.Namespace,
    shell: GPhotoShellSession,
    exposure_config: str | None,
    choices: list[str] | None,
    camera_folder: str,
) -> list[tuple[str, str]] | list[tuple[int, str, str]]:
    if args.mode == "aeb":
        current_index = read_aeb_current_index_in_shell(shell)
        shots_to_take = shots_needed_to_finish_aeb_round(current_index)
        if current_index > 1:
            log(
                f"Continuing partial AEB round from shot {current_index}/{AEB_SHOT_COUNT}; "
                f"{shots_to_take} shot(s) needed to finish"
            )
        else:
            log("Starting a fresh AEB round")
        return capture_aeb_round_in_shell(shell, shots_to_take, camera_folder)

    if exposure_config is None or choices is None:
        raise GPhotoError("Manual mode exposure configuration was not prepared.")

    return capture_manual_round_in_shell(shell, exposure_config, choices, camera_folder)


def capture_all_rounds_in_shell(
    args: argparse.Namespace,
    shell: GPhotoShellSession,
    total_rounds: int | None,
    start_group: int,
    exposure_config: str | None,
    choices: list[str] | None,
    camera_folder: str,
) -> list[list[tuple[str, str]] | list[tuple[int, str, str]]]:
    captured_rounds: list[list[tuple[str, str]] | list[tuple[int, str, str]]] = []
    completed_rounds = 0

    while total_rounds is None or completed_rounds < total_rounds:
        round_number = start_group + completed_rounds
        log(f"Starting capture round {round_number:04d}")
        captured_rounds.append(
            capture_single_round_in_shell(args, shell, exposure_config, choices, camera_folder)
        )
        completed_rounds += 1

        if total_rounds is not None and completed_rounds >= total_rounds:
            break

        if args.interval is not None and args.interval > 0:
            log(f"Waiting {args.interval:g} second(s) before next round")
            time.sleep(args.interval)

    return captured_rounds


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
        return capture_aeb_round(args.gphoto, shots_to_take, dry_run=args.dry_run)

    if exposure_config is None or choices is None:
        raise GPhotoError("Manual mode exposure configuration was not prepared.")

    return capture_manual_round(
        args.gphoto,
        exposure_config,
        choices,
        dry_run=args.dry_run,
    )


def capture_all_rounds(
    args: argparse.Namespace,
    total_rounds: int | None,
    start_group: int,
    exposure_config: str | None,
    choices: list[str] | None,
) -> list[list[tuple[str, str]] | list[tuple[int, str, str]]]:
    captured_rounds: list[list[tuple[str, str]] | list[tuple[int, str, str]]] = []
    completed_rounds = 0

    while total_rounds is None or completed_rounds < total_rounds:
        round_number = start_group + completed_rounds
        log(f"Starting capture round {round_number:04d}")
        captured_rounds.append(capture_single_round(args, exposure_config, choices))
        completed_rounds += 1

        if total_rounds is not None and completed_rounds >= total_rounds:
            break

        if args.interval is not None and args.interval > 0:
            log(f"Waiting {args.interval:g} second(s) before next round")
            time.sleep(args.interval)

    return captured_rounds


def download_all_rounds(
    args: argparse.Namespace,
    output_dir: Path,
    start_group: int,
    captured_rounds: list[list[tuple[str, str]] | list[tuple[int, str, str]]],
) -> None:
    if not captured_rounds:
        return

    log("Capture phase finished; starting download phase")
    if args.mode == "aeb":
        download_aeb_rounds(
            args.gphoto,
            output_dir,
            start_group,
            captured_rounds,  # type: ignore[arg-type]
            dry_run=args.dry_run,
        )
        return

    download_manual_rounds(
        args.gphoto,
        output_dir,
        start_group,
        captured_rounds,  # type: ignore[arg-type]
        dry_run=args.dry_run,
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    validate_args(parser, args)
    args.round_count = maybe_prompt_round_count(args.round_count)

    if not args.dry_run and shutil.which(args.gphoto) is None and not Path(args.gphoto).exists():
        log(
            "gphoto2 was not found. Install gPhoto2 and make sure it is available in PATH, "
            "or pass --gphoto /path/to/gphoto2.",
            level="error",
            file=sys.stderr,
        )
        return 127

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    start_group = next_group_number(output_dir)

    if args.dry_run:
        try:
            with suppress_ptpcamerad():
                exposure_config: str | None = None
                choices: list[str] | None = None
                if args.mode == "manual":
                    exposure_config, choices = prepare_manual_context(args)

                completed_rounds = 0
                while args.round_count is None or completed_rounds < args.round_count:
                    round_number = start_group + completed_rounds
                    log(f"Starting capture round {round_number:04d}")
                    captured_rounds = [
                        capture_single_round(args, exposure_config, choices)
                    ]
                    download_all_rounds(args, output_dir, round_number, captured_rounds)
                    completed_rounds += 1

                    if args.round_count is not None and completed_rounds >= args.round_count:
                        break

                    if args.interval is not None and args.interval > 0:
                        log(f"Waiting {args.interval:g} second(s) before next round")
                        time.sleep(args.interval)
        except KeyboardInterrupt:
            log("Interrupted by user", level="warn", file=sys.stderr)
            return 130
        except GPhotoError as exc:
            log(str(exc), level="error", file=sys.stderr)
            return 1

        log(f"Done. Files downloaded to: {args.output_dir.resolve()}")
        return 0

    try:
        with suppress_ptpcamerad():
            exposure_config: str | None = None
            choices: list[str] | None = None
            if args.mode == "manual":
                exposure_config, choices = prepare_manual_context(args)
            completed_rounds = 0
            while args.round_count is None or completed_rounds < args.round_count:
                round_number = start_group + completed_rounds
                log(f"Starting capture round {round_number:04d}")
                captured_rounds = [
                    capture_single_round(args, exposure_config, choices)
                ]
                download_all_rounds(args, output_dir, round_number, captured_rounds)
                completed_rounds += 1

                if args.round_count is not None and completed_rounds >= args.round_count:
                    break

                if args.interval is not None and args.interval > 0:
                    log(f"Waiting {args.interval:g} second(s) before next round")
                    time.sleep(args.interval)
    except KeyboardInterrupt:
        log("Interrupted by user", level="warn", file=sys.stderr)
        return 130
    except GPhotoError as exc:
        log(str(exc), level="error", file=sys.stderr)
        return 1

    log(f"Done. Files downloaded to: {args.output_dir.resolve()}")
    return 0
