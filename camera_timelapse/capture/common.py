from __future__ import annotations

import re
from pathlib import Path

from camera_timelapse.core.log import log
from camera_timelapse.gphoto import GPhotoError, GPhotoShellSession, run_gphoto
from camera_timelapse.parsing import camera_path


def next_group_number(output_dir: Path) -> int:
    highest = 0
    group_pattern = re.compile(r"^(\d{4})_")

    if not output_dir.exists():
        return 1

    for path in output_dir.iterdir():
        match = group_pattern.match(path.name)
        if match:
            highest = max(highest, int(match.group(1)))

    return highest + 1


def destination_for_capture(output_dir: Path, group: int, index: int, camera_file: str) -> Path:
    suffix = Path(camera_file).suffix or ".jpg"
    return output_dir / f"{group:04d}_{index:02d}{suffix}"


def download_camera_file(
    gphoto: str,
    folder: str,
    camera_file: str,
    destination: Path,
    *,
    dry_run: bool,
) -> None:
    source = camera_path(folder, camera_file)
    log(f"Downloading {source} to {destination}")

    local_source = Path(folder) / camera_file
    if not dry_run and local_source.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        local_source.replace(destination)
        return

    run_gphoto(
        gphoto,
        [
            "--folder",
            folder,
            "--filename",
            str(destination),
            "--get-file",
            camera_file,
            "--force-overwrite",
        ],
        dry_run=dry_run,
    )


def download_camera_file_in_shell(
    shell: GPhotoShellSession,
    folder: str,
    camera_file: str,
    destination: Path,
) -> None:
    temporary_file = shell.working_dir / Path(camera_file).name

    if temporary_file.exists():
        temporary_file.unlink()

    log(f"Downloading {camera_path(folder, camera_file)} to {destination}")
    shell.run(f"cd {folder}")
    shell.run(f"get {camera_file}")

    if not temporary_file.exists():
        raise GPhotoError(f"Downloaded file was not found locally: {temporary_file}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_file.replace(destination)
