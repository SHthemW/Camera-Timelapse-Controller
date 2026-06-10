from __future__ import annotations

import re

from gphoto_timelapse.gphoto import GPhotoError


def parse_choices(config_output: str) -> list[str]:
    choices: list[str] = []
    for line in config_output.splitlines():
        match = re.match(r"\s*Choice:\s+\d+\s+(.+?)\s*$", line)
        if match:
            choices.append(match.group(1).strip())
    return choices


def numbers_from_text(text: str) -> list[float]:
    values: list[float] = []

    for numerator, denominator in re.findall(r"([+-]?\d+)\s*/\s*(\d+)", text):
        denominator_value = int(denominator)
        if denominator_value:
            values.append(int(numerator) / denominator_value)

    for value in re.findall(r"(?<!/)([+-]?\d+(?:\.\d+)?)(?!\s*/)", text):
        values.append(float(value))

    return values


def choice_for_ev(choices: list[str], ev: float) -> str:
    if not choices:
        return format_ev(ev)

    exact_tokens = {
        f"{ev:g}",
        f"{ev:+g}",
        f"{ev:.1f}",
        f"{ev:+.1f}",
        f"{ev:g} EV",
        f"{ev:+g} EV",
        f"{ev:g}EV",
        f"{ev:+g}EV",
    }

    for choice in choices:
        normalized = choice.replace("ev", "EV")
        if normalized in exact_tokens:
            return choice

    for choice in choices:
        for value in numbers_from_text(choice):
            if abs(value - ev) < 0.001:
                return choice

    available = ", ".join(choices)
    raise GPhotoError(f"Camera does not expose a {format_ev(ev)} choice. Choices: {available}")


def format_ev(ev: float) -> str:
    if ev > 0:
        return f"+{ev:g}"
    return f"{ev:g}"


def parse_camera_file(capture_output: str) -> tuple[str, str]:
    camera_files = parse_camera_files(capture_output)
    if not camera_files:
        raise GPhotoError(f"Could not find captured camera file in gPhoto2 output:\n{capture_output}")
    return camera_files[0]


def parse_camera_files(capture_output: str) -> list[tuple[str, str]]:
    patterns = (
        r"New file is in location\s+(.+?)\s+on the camera",
        r"新文件在相机中\s+(.+?)\s+处",
    )
    camera_files: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for pattern in patterns:
        for match in re.finditer(pattern, capture_output):
            camera_file = split_camera_path(match.group(1).strip())
            if camera_file not in seen:
                camera_files.append(camera_file)
                seen.add(camera_file)

    return camera_files


def split_camera_path(camera_path: str) -> tuple[str, str]:
    if "/" not in camera_path:
        return "/", camera_path

    folder, filename = camera_path.rsplit("/", 1)
    return folder or "/", filename


def parse_list_files(output: str) -> tuple[str, list[str]]:
    folder_header = re.compile(r"^There (?:is|are) \d+ file[s]? in folder '(.+)'\.")
    file_entry = re.compile(r"^#\d+\s+(\S+)\s+")

    current_folder = ""
    current_files: list[str] = []
    last_folder = ""
    last_files: list[str] = []

    for line in output.splitlines():
        header_match = folder_header.match(line.strip())
        if header_match:
            if current_folder and current_files:
                last_folder = current_folder
                last_files = current_files
            current_folder = header_match.group(1)
            current_files = []
            continue

        file_match = file_entry.match(line.strip())
        if file_match and current_folder:
            current_files.append(file_match.group(1))

    if current_folder and current_files:
        last_folder = current_folder
        last_files = current_files

    if not last_folder or not last_files:
        raise GPhotoError(f"Could not determine latest camera folder from gPhoto2 output:\n{output}")

    return last_folder, last_files


def camera_path(folder: str, camera_file: str) -> str:
    if folder == "/":
        return f"/{camera_file}"
    return f"{folder.rstrip('/')}/{camera_file}"


def format_camera_files(camera_files: list[tuple[str, str]]) -> str:
    return ", ".join(camera_path(folder, camera_file) for folder, camera_file in camera_files)
