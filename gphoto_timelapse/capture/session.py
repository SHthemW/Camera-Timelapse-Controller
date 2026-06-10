from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Union

from gphoto_timelapse.camera.config import (
    read_aeb_current_index_in_shell,
    shots_needed_to_finish_aeb_round,
)
from gphoto_timelapse.capture.aeb import capture_aeb_round_in_shell
from gphoto_timelapse.capture.common import destination_for_capture
from gphoto_timelapse.core.constants import AEB_SHOT_COUNT
from gphoto_timelapse.capture.manual import capture_manual_round_in_shell
from gphoto_timelapse.core.log import log
from gphoto_timelapse.gphoto import GPhotoError, GPhotoShellSession


CapturedRound = Union[list[tuple[str, str]], list[tuple[int, str, str]]]


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
) -> list[CapturedRound]:
    download_temp_dir = Path.cwd() / ".download_tmp"
    if download_temp_dir.exists():
        shutil.rmtree(download_temp_dir)
    download_temp_dir.mkdir(parents=True, exist_ok=True)

    captured_rounds: list[CapturedRound] = []

    try:
        with GPhotoShellSession(gphoto, download_temp_dir, extra_args=["--keep"]) as shell:
            captured_rounds = capture_all_rounds_in_shell(
                shell,
                total_rounds,
                start_group,
                interval,
                mode,
                exposure_config,
                choices,
            )
            if captured_rounds:
                log("Capture phase finished; starting download phase")
        if captured_rounds:
            download_all_rounds_in_shell(output_dir, start_group, captured_rounds)
    finally:
        shutil.rmtree(download_temp_dir, ignore_errors=True)

    return captured_rounds


def capture_all_rounds_in_shell(
    shell: GPhotoShellSession,
    total_rounds: int | None,
    start_group: int,
    interval: float | None,
    mode: str,
    exposure_config: str | None,
    choices: list[str] | None,
) -> list[CapturedRound]:
    captured_rounds: list[CapturedRound] = []
    completed_rounds = 0

    while total_rounds is None or completed_rounds < total_rounds:
        round_number = start_group + completed_rounds
        log(f"Starting capture round {round_number:04d}")
        captured_rounds.append(
            capture_single_round_in_shell(shell, mode, exposure_config, choices)
        )
        completed_rounds += 1

        if total_rounds is not None and completed_rounds >= total_rounds:
            break

        if interval is not None and interval > 0:
            log(f"Waiting {interval:g} second(s) before next round")
            time.sleep(interval)

    return captured_rounds


def capture_single_round_in_shell(
    shell: GPhotoShellSession,
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
        return capture_aeb_round_in_shell(shell, shots_to_take)

    if exposure_config is None or choices is None:
        raise GPhotoError("Manual mode exposure configuration was not prepared.")

    return capture_manual_round_in_shell(shell, exposure_config, choices)


def download_all_rounds_in_shell(
    output_dir: Path,
    start_group: int,
    captured_rounds: list[CapturedRound],
) -> None:
    for group_offset, captured_files in enumerate(captured_rounds):
        group = start_group + group_offset
        if not captured_files:
            continue

        first_item = captured_files[0]
        if len(first_item) == 2:
            for index, (folder, camera_file) in enumerate(captured_files, start=1):
                destination = destination_for_capture(output_dir, group, index, camera_file)
                local_source = Path(folder) / camera_file
                if not local_source.exists():
                    raise GPhotoError(f"Downloaded file was not found locally: {local_source}")
                destination.parent.mkdir(parents=True, exist_ok=True)
                local_source.replace(destination)
            continue

        for index, folder, camera_file in captured_files:
            destination = destination_for_capture(output_dir, group, index, camera_file)
            local_source = Path(folder) / camera_file
            if not local_source.exists():
                raise GPhotoError(f"Downloaded file was not found locally: {local_source}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            local_source.replace(destination)
