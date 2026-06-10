from __future__ import annotations

import time
from pathlib import Path

from .capture_common import (
    destination_for_capture,
    download_camera_file,
    next_group_number,
    remove_empty_temp_dir,
)
from .constants import BRACKET_STOPS, DRY_RUN_CAPTURE_FOLDER
from .gphoto import GPhotoShellSession, run_gphoto
from .log import current_timestamp, log
from .parsing import choice_for_ev, format_ev, parse_camera_file, parse_choices


def capture_bracket(
    gphoto: str,
    output_dir: Path,
    exposure_config: str,
    *,
    dry_run: bool,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    config_output = run_gphoto(gphoto, ["--get-config", exposure_config], dry_run=dry_run)
    choices = parse_choices(config_output)
    group = next_group_number(output_dir)
    group_started_at = current_timestamp()
    group_started = time.monotonic()

    log(f"Starting group {group:04d}")

    captured_files: list[tuple[int, str, str]] = []

    if dry_run:
        capture_manual_dry_run(gphoto, output_dir, exposure_config, choices, group, captured_files)
    else:
        capture_manual_files(gphoto, output_dir, exposure_config, choices, group, captured_files)

    elapsed = time.monotonic() - group_started
    log(
        f"Finished group {group:04d}; capture time: {elapsed:.1f} seconds; "
        f"started at {group_started_at}; finished at {current_timestamp()}"
    )


def capture_to_camera(
    gphoto: str,
    exposure_config: str,
    config_value: str,
    ev: float,
    *,
    dry_run: bool,
) -> tuple[str, str]:
    log(f"Setting exposure compensation to {format_ev(ev)} EV")
    run_gphoto(gphoto, ["--set-config", f"{exposure_config}={config_value}"], dry_run=dry_run)

    log("Capturing to camera storage")
    output = run_gphoto(gphoto, ["--capture-image"], dry_run=dry_run)
    if dry_run:
        filename = f"dry-run-{format_ev(ev).replace('+', 'plus').replace('-', 'minus')}.jpg"
        return DRY_RUN_CAPTURE_FOLDER, filename

    return parse_camera_file(output)


def capture_to_camera_in_shell(
    shell: GPhotoShellSession,
    exposure_config: str,
    config_value: str,
    ev: float,
) -> tuple[str, str]:
    log(f"Setting exposure compensation to {format_ev(ev)} EV")
    shell.run(f"set-config {exposure_config}={config_value}")

    log("Capturing to camera storage")
    output = shell.run("capture-image")
    return parse_camera_file(output)


def capture_manual_dry_run(
    gphoto: str,
    output_dir: Path,
    exposure_config: str,
    choices: list[str],
    group: int,
    captured_files: list[tuple[int, str, str]],
) -> None:
    for index, ev in enumerate(BRACKET_STOPS, start=1):
        value = choice_for_ev(choices, ev)
        folder, camera_file = capture_to_camera(
            gphoto,
            exposure_config,
            value,
            ev,
            dry_run=True,
        )
        captured_files.append((index, folder, camera_file))

    for index, folder, camera_file in captured_files:
        stem = f"{group:04d}_{index:02d}"
        destination = output_dir / f"{stem}.%C"
        download_camera_file(gphoto, folder, camera_file, destination, dry_run=True)


def capture_manual_files(
    gphoto: str,
    output_dir: Path,
    exposure_config: str,
    choices: list[str],
    group: int,
    captured_files: list[tuple[int, str, str]],
) -> None:
    download_temp_dir = output_dir / ".download_tmp"
    download_temp_dir.mkdir(parents=True, exist_ok=True)

    with GPhotoShellSession(gphoto, download_temp_dir) as shell:
        for index, ev in enumerate(BRACKET_STOPS, start=1):
            value = choice_for_ev(choices, ev)
            folder, camera_file = capture_to_camera_in_shell(
                shell,
                exposure_config,
                value,
                ev,
            )
            captured_files.append((index, folder, camera_file))

        for index, folder, camera_file in captured_files:
            destination = destination_for_capture(output_dir, group, index, camera_file)
            download_camera_file(gphoto, folder, camera_file, destination, dry_run=False)

    remove_empty_temp_dir(download_temp_dir)

