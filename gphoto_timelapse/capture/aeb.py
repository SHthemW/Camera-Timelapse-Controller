from __future__ import annotations

import time
from pathlib import Path

from gphoto_timelapse.camera.config import (
    latest_dcim_folder,
    read_aeb_current_index,
    shots_needed_to_finish_aeb_round,
)
from gphoto_timelapse.capture.common import (
    destination_for_capture,
    download_camera_file,
    download_camera_file_in_shell,
    next_group_number,
    remove_empty_temp_dir,
)
from gphoto_timelapse.core.constants import AEB_SHOT_COUNT
from gphoto_timelapse.core.log import current_timestamp, log
from gphoto_timelapse.gphoto import GPhotoError, GPhotoShellSession, run_gphoto
from gphoto_timelapse.parsing import format_camera_files, parse_camera_files, parse_list_files


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

    if dry_run:
        capture_aeb_dry_run(gphoto, output_dir, group, shots_to_take)
    else:
        capture_aeb_files(gphoto, output_dir, group, shots_to_take)

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


def capture_aeb_dry_run(
    gphoto: str,
    output_dir: Path,
    group: int,
    shots_to_take: int,
) -> list[tuple[str, str]]:
    for shot_index in range(1, shots_to_take + 1):
        log(f"Capturing AEB shot {shot_index}/{shots_to_take} to camera storage")

    selected_files = [
        ("/store_00010001/DCIM/172NZ_30", "dry-run-aeb-1.jpg"),
        ("/store_00010001/DCIM/172NZ_30", "dry-run-aeb-2.jpg"),
        ("/store_00010001/DCIM/172NZ_30", "dry-run-aeb-3.jpg"),
    ]
    log(f"Using captured AEB file paths: {format_camera_files(selected_files)}")

    for index, (folder, camera_file) in enumerate(selected_files, start=1):
        destination = destination_for_capture(output_dir, group, index, camera_file)
        download_camera_file(
            gphoto,
            folder,
            camera_file,
            destination,
            dry_run=True,
        )

    return selected_files


def capture_aeb_files(
    gphoto: str,
    output_dir: Path,
    group: int,
    shots_to_take: int,
) -> list[tuple[str, str]]:
    download_temp_dir = output_dir / ".download_tmp"
    download_temp_dir.mkdir(parents=True, exist_ok=True)

    captured_files: list[tuple[str, str]] = []
    downloaded_in_shell = False
    selected_files: list[tuple[str, str]] = []

    with GPhotoShellSession(gphoto, download_temp_dir) as shell:
        for shot_index in range(1, shots_to_take + 1):
            log(f"Capturing AEB shot {shot_index}/{shots_to_take} to camera storage")
            output = shell.run("capture-image")
            shot_files = parse_camera_files(output)
            captured_files.extend(shot_files)
            if shot_files:
                log(f"Captured AEB file path(s): {format_camera_files(shot_files)}")
            else:
                log(
                    f"AEB shot {shot_index}/{shots_to_take} completed without a file path in output",
                    level="warn",
                )

        if len(captured_files) >= AEB_SHOT_COUNT:
            selected_files = captured_files[-AEB_SHOT_COUNT:]
            log(f"Using captured AEB file paths: {format_camera_files(selected_files)}")
            for index, (folder, camera_file) in enumerate(selected_files, start=1):
                destination = destination_for_capture(output_dir, group, index, camera_file)
                download_camera_file_in_shell(shell, folder, camera_file, destination)
            downloaded_in_shell = True

    remove_empty_temp_dir(download_temp_dir)

    if downloaded_in_shell:
        return selected_files

    return download_latest_aeb_files(gphoto, output_dir, group)


def download_latest_aeb_files(
    gphoto: str,
    output_dir: Path,
    group: int,
) -> list[tuple[str, str]]:
    log("Capture output did not list all AEB files; falling back to camera folder scan", level="warn")
    folder = latest_dcim_folder(gphoto, dry_run=False)
    log(f"Inspecting camera folder: {folder}")
    output = run_gphoto(
        gphoto,
        ["--folder", folder, "--list-files"],
        dry_run=False,
    )
    folder, camera_files = parse_list_files(output)
    if len(camera_files) < AEB_SHOT_COUNT:
        raise GPhotoError(
            f"AEB capture produced {len(camera_files)} visible file(s), "
            f"expected at least {AEB_SHOT_COUNT}."
        )

    selected_files = [(folder, camera_file) for camera_file in camera_files[-AEB_SHOT_COUNT:]]
    log(f"Selected latest AEB files from {folder}: {', '.join(camera_files[-AEB_SHOT_COUNT:])}")

    for index, (folder, camera_file) in enumerate(selected_files, start=1):
        destination = destination_for_capture(output_dir, group, index, camera_file)
        download_camera_file(
            gphoto,
            folder,
            camera_file,
            destination,
            dry_run=False,
        )

    return selected_files
