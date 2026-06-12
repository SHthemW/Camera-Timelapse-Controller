from __future__ import annotations

import datetime as dt
from pathlib import Path

from camera_timelapse.camera.config import (
    read_aeb_current_index_in_shell,
    shots_needed_to_finish_aeb_round,
)
from camera_timelapse.capture.aeb import capture_aeb_round_in_shell
from camera_timelapse.core.constants import AEB_SHOT_COUNT
from camera_timelapse.capture.manual import capture_manual_round_in_shell
from camera_timelapse.capture.timing import (
    current_interval_timestamp,
    wait_for_next_round,
)
from camera_timelapse.core.log import log
from camera_timelapse.core.schedule import has_reached_scheduled_time, scheduled_datetime
from camera_timelapse.gphoto import GPhotoError, GPhotoShellSession


CapturedRound = list[tuple[int, str, str]]


def run_capture_and_download_session(
    *,
    gphoto: str,
    output_dir: Path,
    start_group: int,
    total_rounds: int | None,
    interval: float | None,
    mode: str,
    exposure_config: str | None,
    choices: list[str] | None,
    end_at: dt.time | None,
    end_day: dt.date | None,
) -> list[CapturedRound]:
    captured_rounds: list[CapturedRound] = []

    with GPhotoShellSession(gphoto, output_dir) as shell:
        captured_rounds = capture_all_rounds_in_shell(
            shell,
            output_dir,
            total_rounds,
            start_group,
            interval,
            mode,
            exposure_config,
            choices,
            end_at,
            end_day,
        )

    return captured_rounds


def capture_all_rounds_in_shell(
    shell: GPhotoShellSession,
    output_dir: Path,
    total_rounds: int | None,
    start_group: int,
    interval: float | None,
    mode: str,
    exposure_config: str | None,
    choices: list[str] | None,
    end_at: dt.time | None,
    end_day: dt.date | None,
) -> list[CapturedRound]:
    captured_rounds: list[CapturedRound] = []
    completed_rounds = 0

    while total_rounds is None or completed_rounds < total_rounds:
        round_started_at = current_interval_timestamp()
        round_number = start_group + completed_rounds
        log(f"Starting capture round {round_number:04d}")
        captured_files = capture_single_round_in_shell(
            shell,
            output_dir,
            round_number,
            mode,
            exposure_config,
            choices,
        )
        captured_rounds.append(captured_files)
        completed_rounds += 1

        if total_rounds is not None and completed_rounds >= total_rounds:
            break

        if end_at is not None and has_reached_scheduled_time(end_at, end_day):
            log(
                f"Scheduled end time {scheduled_datetime(end_at, end_day):%Y-%m-%d %H:%M} "
                "reached; stopping after this round"
            )
            break

        wait_for_next_round(round_started_at, interval)

    return captured_rounds


def capture_single_round_in_shell(
    shell: GPhotoShellSession,
    output_dir: Path,
    group: int,
    mode: str,
    exposure_config: str | None,
    choices: list[str] | None,
) -> CapturedRound:
    if mode == "aeb":
        current_index = read_aeb_current_index_in_shell(shell)
        shots_to_take = shots_needed_to_finish_aeb_round(current_index)
        if current_index > 1:
            log(
                f"Continuing partial AEB round from shot {current_index}/{AEB_SHOT_COUNT}; "
                f"{shots_to_take} shot(s) needed to finish"
            )
        else:
            log("Starting a fresh AEB round")
        return capture_aeb_round_in_shell(
            shell,
            shots_to_take,
            start_capture_order=current_index,
            output_dir=output_dir,
            group=group,
        )

    if exposure_config is None or choices is None:
        raise GPhotoError("Manual mode exposure configuration was not prepared.")

    return capture_manual_round_in_shell(
        shell,
        output_dir,
        group,
        exposure_config,
        choices,
    )
