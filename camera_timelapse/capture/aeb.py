from __future__ import annotations

import time
from pathlib import Path

from camera_timelapse.camera.config import (
    read_aeb_current_index,
    shots_needed_to_finish_aeb_round,
)
from camera_timelapse.capture.common import (
    destination_for_capture,
    download_camera_file_in_shell,
    download_camera_file,
    next_group_number,
)
from camera_timelapse.core.constants import AEB_SHOT_COUNT
from camera_timelapse.core.log import current_timestamp, log
from camera_timelapse.gphoto import GPhotoError, GPhotoShellSession, run_gphoto
from camera_timelapse.parsing import format_camera_files, parse_camera_files


CapturedFiles = list[tuple[int, str, str]]
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
        start_capture_order=current_index,
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
    start_capture_order: int = 1,
    dry_run: bool,
) -> CapturedFiles:
    if dry_run:
        return capture_aeb_dry_run(shots_to_take, start_capture_order)

    with GPhotoShellSession(gphoto, Path.cwd()) as shell:
        return capture_aeb_round_in_shell(
            shell,
            shots_to_take,
            start_capture_order=start_capture_order,
        )


def capture_aeb_round_in_shell(
    shell: GPhotoShellSession,
    shots_to_take: int,
    *,
    start_capture_order: int = 1,
    output_dir: Path | None = None,
    group: int | None = None,
) -> CapturedFiles:
    if (output_dir is None) != (group is None):
        raise GPhotoError("output_dir and group must be provided together.")

    captured_files: CapturedFiles = []

    for shot_index in range(1, shots_to_take + 1):
        capture_order = start_capture_order + shot_index - 1
        log(f"Capturing AEB shot {shot_index}/{shots_to_take} to camera storage")
        output = shell.run("capture-image")
        shot_files = parse_camera_files(output)
        if len(shot_files) != 1:
            log(
                f"AEB shot {shot_index}/{shots_to_take} returned {len(shot_files)} file path(s): "
                f"{format_camera_files(shot_files)}",
                level="warn",
            )
            raise GPhotoError(
                f"AEB shot {shot_index}/{shots_to_take} did not return exactly one file path."
            )

        source_folder, source_name = shot_files[0]
        if output_dir is not None and group is not None:
            destination = destination_for_capture(output_dir, group, capture_order, source_name)
            download_camera_file_in_shell(
                shell,
                source_folder,
                source_name,
                destination,
            )
            captured_files.append((capture_order, str(output_dir), destination.name))
            continue

        captured_files.append((capture_order, source_folder, source_name))
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
            for index, folder, camera_file in selected_files:
                destination = destination_for_capture(output_dir, group, index, camera_file)
                download_camera_file(gphoto, folder, camera_file, destination, dry_run=True)
        return

    for group_offset, selected_files in enumerate(captured_rounds):
        group = start_group + group_offset
        for index, folder, camera_file in selected_files:
            destination = destination_for_capture(output_dir, group, index, camera_file)
            local_source = Path(folder) / camera_file
            if not local_source.exists():
                raise GPhotoError(f"Downloaded file was not found locally: {local_source}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            local_source.replace(destination)


def capture_aeb_dry_run(shots_to_take: int, start_capture_order: int = 1) -> CapturedFiles:
    for shot_index in range(1, shots_to_take + 1):
        log(f"Capturing AEB shot {shot_index}/{shots_to_take} to camera storage")

    selected_files: CapturedFiles = [
        (1, "/store_00010001/DCIM/172NZ_30", "dry-run-aeb-1.jpg"),
        (2, "/store_00010001/DCIM/172NZ_30", "dry-run-aeb-2.jpg"),
        (3, "/store_00010001/DCIM/172NZ_30", "dry-run-aeb-3.jpg"),
    ]
    selected_files = selected_files[start_capture_order - 1 : start_capture_order - 1 + shots_to_take]
    log(f"Using captured AEB file paths: {format_camera_files([(folder, name) for _, folder, name in selected_files])}")
    return selected_files
