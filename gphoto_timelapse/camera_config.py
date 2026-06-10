from __future__ import annotations

import re

from .constants import AEB_SHOT_COUNT, DEFAULT_CONFIG_CANDIDATES
from .gphoto import GPhotoError, run_gphoto


def find_exposure_config(gphoto: str, override: str | None, *, dry_run: bool) -> str:
    if override:
        return override

    if dry_run:
        return DEFAULT_CONFIG_CANDIDATES[0]

    for candidate in DEFAULT_CONFIG_CANDIDATES:
        try:
            run_gphoto(gphoto, ["--get-config", candidate])
        except GPhotoError:
            continue
        return candidate

    try:
        config_list = run_gphoto(gphoto, ["--list-config"])
    except GPhotoError as exc:
        raise GPhotoError("Unable to list camera configuration entries.") from exc

    for line in config_list.splitlines():
        path = line.strip()
        if path and "exposurecompensation" in path.lower():
            return path

    raise GPhotoError(
        "Could not find an exposure compensation setting. "
        "Run `gphoto2 --list-config` and pass the correct path with --config."
    )


def read_aeb_current_index(gphoto: str, *, dry_run: bool) -> int:
    if dry_run:
        return 1

    output = run_gphoto(gphoto, ["--get-config", "/main/other/d0c3"], dry_run=dry_run)
    match = re.search(r"Current:\s+(\d+)", output)
    if not match:
        raise GPhotoError(f"Could not read AEB current shot index from gPhoto2 output:\n{output}")

    return int(match.group(1))


def shots_needed_to_finish_aeb_round(current_index: int) -> int:
    if current_index < 1 or current_index > AEB_SHOT_COUNT:
        raise GPhotoError(
            f"Camera reports AEB current shot index {current_index}, "
            f"expected 1-{AEB_SHOT_COUNT}."
        )

    return AEB_SHOT_COUNT - current_index + 1


def read_storage_basedir(gphoto: str, *, dry_run: bool) -> str:
    if dry_run:
        return "/store_00010001"

    output = run_gphoto(gphoto, ["--storage-info"], dry_run=dry_run)
    match = re.search(r"basedir=(\S+)", output)
    if not match:
        raise GPhotoError(f"Could not read storage base directory from gPhoto2 output:\n{output}")

    return match.group(1)


def latest_dcim_folder(gphoto: str, *, dry_run: bool) -> str:
    if dry_run:
        return "/store_00010001/DCIM/172NZ_30"

    basedir = read_storage_basedir(gphoto, dry_run=dry_run)
    output = run_gphoto(gphoto, ["--folder", f"{basedir}/DCIM", "--list-folders"], dry_run=dry_run)
    folders = re.findall(r"^\s*-\s+(\S+)\s*$", output, flags=re.MULTILINE)
    if not folders:
        raise GPhotoError(f"Could not determine latest DCIM folder from gPhoto2 output:\n{output}")

    return f"{basedir}/DCIM/{folders[-1]}"

