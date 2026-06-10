from __future__ import annotations

import time
from pathlib import Path

from gphoto_timelapse.capture.common import (
    destination_for_capture,
    download_camera_file,
    next_group_number,
    remove_empty_temp_dir,
)
from gphoto_timelapse.camera.config import latest_dcim_folder
from gphoto_timelapse.core.constants import BRACKET_STOPS, DRY_RUN_CAPTURE_FOLDER
from gphoto_timelapse.core.log import current_timestamp, log
from gphoto_timelapse.gphoto import GPhotoShellSession, run_gphoto
from gphoto_timelapse.parsing import choice_for_ev, format_ev, parse_camera_file, parse_choices


CapturedFiles = list[tuple[int, str, str]]
CapturedRounds = list[CapturedFiles]


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
    captured_files = capture_manual_round(
        gphoto,
        exposure_config,
        choices,
        dry_run=dry_run,
    )
    download_manual_rounds(
        gphoto,
        output_dir,
        group,
        [captured_files],
        dry_run=dry_run,
    )

    elapsed = time.monotonic() - group_started
    log(
        f"Finished group {group:04d}; capture time: {elapsed:.1f} seconds; "
        f"started at {group_started_at}; finished at {current_timestamp()}"
    )


def capture_manual_round(
    gphoto: str,
    exposure_config: str,
    choices: list[str],
    *,
    dry_run: bool,
    camera_folder: str | None = None,
) -> CapturedFiles:
    if dry_run:
        captured_files: CapturedFiles = []
        capture_manual_dry_run(
            gphoto,
            exposure_config,
            choices,
            captured_files,
        )
        return captured_files

    if camera_folder is None:
        camera_folder = latest_dcim_folder(gphoto, dry_run=False)

    download_temp_dir = Path.cwd() / ".download_tmp"
    download_temp_dir.mkdir(parents=True, exist_ok=True)

    with GPhotoShellSession(gphoto, download_temp_dir) as shell:
        return capture_manual_round_in_shell(shell, exposure_config, choices, camera_folder)


def capture_manual_round_in_shell(
    shell: GPhotoShellSession,
    exposure_config: str,
    choices: list[str],
    camera_folder: str,
) -> CapturedFiles:
    shell.run(f"cd {camera_folder}")
    local_dir = shell.working_dir
    captured_files: CapturedFiles = []
    for index, ev in enumerate(BRACKET_STOPS, start=1):
        value = choice_for_ev(choices, ev)
        before = {path.name for path in local_dir.iterdir() if path.is_file()}
        output = capture_to_camera_in_shell(
            shell,
            exposure_config,
            value,
            ev,
        )
        shot_files = parse_camera_file(output)
        after = sorted(
            path for path in local_dir.iterdir() if path.is_file() and path.name not in before
        )
        if len(after) != 1:
            raise GPhotoError(
                f"Manual shot {index}/{len(BRACKET_STOPS)} downloaded {len(after)} local file(s), "
                "expected exactly 1."
            )
        captured_files.append((str(local_dir), after[0].name))

    return captured_files


def download_manual_rounds(
    gphoto: str,
    output_dir: Path,
    start_group: int,
    captured_rounds: CapturedRounds,
    *,
    dry_run: bool,
) -> None:
    if dry_run:
        for group_offset, captured_files in enumerate(captured_rounds):
            group = start_group + group_offset
            for index, folder, camera_file in captured_files:
                destination = destination_for_capture(output_dir, group, index, camera_file)
                download_camera_file(gphoto, folder, camera_file, destination, dry_run=True)
        return

    local_dirs: set[Path] = set()
    for group_offset, captured_files in enumerate(captured_rounds):
        group = start_group + group_offset
        for index, folder, camera_file in captured_files:
            destination = destination_for_capture(output_dir, group, index, camera_file)
            download_camera_file(gphoto, folder, camera_file, destination, dry_run=False)
            local_dirs.add(Path(folder))

    for local_dir in local_dirs:
        remove_empty_temp_dir(local_dir)


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
    output = shell.run("capture-image-and-download")
    return parse_camera_file(output)


def capture_manual_dry_run(
    gphoto: str,
    exposure_config: str,
    choices: list[str],
    captured_files: CapturedFiles,
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
