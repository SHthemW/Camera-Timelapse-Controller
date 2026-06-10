from __future__ import annotations

import time
from pathlib import Path

from camera_timelapse.camera.config import (
    read_aeb_current_index,
    shots_needed_to_finish_aeb_round,
)
from camera_timelapse.capture.common import (
    destination_for_capture,
    download_camera_file,
    next_group_number,
)
from camera_timelapse.core.constants import AEB_SHOT_COUNT
from camera_timelapse.core.log import current_timestamp, log
from camera_timelapse.gphoto import GPhotoError, GPhotoShellSession, run_gphoto
from camera_timelapse.parsing import format_camera_files, parse_camera_files


CapturedFiles = list[tuple[str, str]]
CapturedRounds = list[CapturedFiles]


def capture_aeb_bracket(
    gphoto: str,
    output_dir: Path,
    *,
    dry_run: bool,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    group = next_group_number(output_dir)
    group_started_at = current_timestamp()
    group_started = time.monotonic()

    log(f"Starting AEB group {group:04d}")

    current_index = read_aeb_current_index(gphoto, dry_run=dry_run)
    shots_to_take = shots_needed_to_finish_aeb_round(current_index)

    if current_index > 1:
        log(
            f"Continuing partial AEB round from shot {current_index}/{AEB_SHOT_COUNT}; "
            f"{shots_to_take} shot(s) needed to finish"
        )
    else:
        log("Starting a fresh AEB round")

    captured_files = capture_aeb_round(
        gphoto,
        shots_to_take,
        dry_run=dry_run,
    )
    download_aeb_rounds(
        gphoto,
        output_dir,
        group,
        [captured_files],
        dry_run=dry_run,
    )

    if not dry_run:
        post_current_index = read_aeb_current_index(gphoto, dry_run=False)
        if post_current_index != 1:
            raise GPhotoError(
                "AEB round finished but camera reports current shot index "
                f"{post_current_index}, expected 1."
            )

    elapsed = time.monotonic() - group_started
    log(
        f"Finished AEB group {group:04d}; capture time: {elapsed:.1f} seconds; "
        f"started at {group_started_at}; finished at {current_timestamp()}"
    )


def capture_aeb_round(
    gphoto: str,
    shots_to_take: int,
    *,
    dry_run: bool,
) -> CapturedFiles:
    if dry_run:
        captured_files = capture_aeb_dry_run(shots_to_take)
        return captured_files[-shots_to_take:]

    with GPhotoShellSession(gphoto, Path.cwd(), extra_args=["--keep"]) as shell:
        return capture_aeb_round_in_shell(shell, shots_to_take)


def capture_aeb_round_in_shell(
    shell: GPhotoShellSession,
    shots_to_take: int,
) -> CapturedFiles:
    captured_files: CapturedFiles = []
    local_dir = shell.working_dir

    for shot_index in range(1, shots_to_take + 1):
        log(f"Capturing AEB shot {shot_index}/{shots_to_take} to camera storage")
        before = {path.name for path in local_dir.iterdir() if path.is_file()}
        output = shell.run("capture-image-and-download")
        shot_files = parse_camera_files(output)
        if shot_files:
            log(f"Captured AEB file path(s): {format_camera_files(shot_files)}")
        else:
            log(
                f"AEB shot {shot_index}/{shots_to_take} completed without a file path in output",
                level="warn",
            )
        after = sorted(
            path for path in local_dir.iterdir() if path.is_file() and path.name not in before
        )
        if len(after) != 1:
            raise GPhotoError(
                f"AEB shot {shot_index}/{shots_to_take} downloaded {len(after)} local file(s), "
                "expected exactly 1."
            )
        captured_files.append((str(local_dir), after[0].name))
    return captured_files


def download_aeb_rounds(
    gphoto: str,
    output_dir: Path,
    start_group: int,
    captured_rounds: CapturedRounds,
    *,
    dry_run: bool,
) -> None:
    if dry_run:
        for group_offset, selected_files in enumerate(captured_rounds):
            group = start_group + group_offset
            for index, (folder, camera_file) in enumerate(selected_files, start=1):
                destination = destination_for_capture(output_dir, group, index, camera_file)
                download_camera_file(gphoto, folder, camera_file, destination, dry_run=True)
        return

    for group_offset, selected_files in enumerate(captured_rounds):
        group = start_group + group_offset
        for index, (folder, camera_file) in enumerate(selected_files, start=1):
            destination = destination_for_capture(output_dir, group, index, camera_file)
            local_source = Path(folder) / camera_file
            if not local_source.exists():
                raise GPhotoError(f"Downloaded file was not found locally: {local_source}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            local_source.replace(destination)


def capture_aeb_dry_run(shots_to_take: int) -> CapturedFiles:
    for shot_index in range(1, shots_to_take + 1):
        log(f"Capturing AEB shot {shot_index}/{shots_to_take} to camera storage")

    selected_files = [
        ("/store_00010001/DCIM/172NZ_30", "dry-run-aeb-1.jpg"),
        ("/store_00010001/DCIM/172NZ_30", "dry-run-aeb-2.jpg"),
        ("/store_00010001/DCIM/172NZ_30", "dry-run-aeb-3.jpg"),
    ]
    log(f"Using captured AEB file paths: {format_camera_files(selected_files)}")
    return selected_files
