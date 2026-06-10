#!/usr/bin/env python3
"""
Capture a three-shot exposure bracket with gPhoto2.

The script sets exposure compensation to +1 EV, 0 EV, and -1 EV, captures one
image at each setting, and downloads the files into ./capture next to this file.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path


DEFAULT_CONFIG_CANDIDATES = (
    "/main/capturesettings/exposurecompensation",
    "/main/imgsettings/exposurecompensation",
    "/main/settings/exposurecompensation",
    "exposurecompensation",
)

BRACKET_STOPS = (1.0, 0.0, -1.0)
DRY_RUN_CAPTURE_FOLDER = "/dry-run"
SHELL_PROMPT_PATTERN = re.compile(r"(?:^|\n)gphoto2: .*?> $", re.DOTALL)


class GPhotoError(RuntimeError):
    """Raised when a gPhoto2 command fails or camera settings are unsupported."""


class GPhotoShellSession:
    def __init__(self, gphoto: str, working_dir: Path) -> None:
        self.working_dir = working_dir
        self.process = subprocess.Popen(
            [gphoto, "--shell"],
            cwd=str(working_dir),
            env=gphoto_environment(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=0,
        )
        self._read_until_prompt()

    def __enter__(self) -> "GPhotoShellSession":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def close(self) -> None:
        if self.process.poll() is not None:
            return

        try:
            if self.process.stdin is not None:
                self.process.stdin.write("quit\n")
                self.process.stdin.flush()
        finally:
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()

    def run(self, command: str, *, check: bool = True) -> str:
        if self.process.stdin is None:
            raise GPhotoError("gPhoto2 shell stdin is unavailable.")

        self.process.stdin.write(f"{command}\n")
        self.process.stdin.flush()
        output = self._read_until_prompt()

        if check and "*** Error" in output:
            raise GPhotoError(f"Command failed in gPhoto2 shell: {command}\n{output.strip()}")

        return output

    def _read_until_prompt(self) -> str:
        if self.process.stdout is None:
            raise GPhotoError("gPhoto2 shell stdout is unavailable.")

        output = []
        while True:
            character = self.process.stdout.read(1)
            if character == "":
                detail = "".join(output).strip()
                raise GPhotoError(f"gPhoto2 shell exited unexpectedly.\n{detail}")

            output.append(character)
            text = "".join(output)
            if SHELL_PROMPT_PATTERN.search(text):
                return text


def current_timestamp() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(message: str, *, file=None) -> None:
    if file is None:
        file = sys.stdout
    print(f"[{current_timestamp()}] {message}", file=file)


def gphoto_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment["LC_ALL"] = "C"
    environment["LANGUAGE"] = "C"
    return environment


def run_gphoto(gphoto: str, args: list[str], *, dry_run: bool = False) -> str:
    command = [gphoto, *args]
    printable = " ".join(command)

    if dry_run:
        log(f"[dry-run] {printable}")
        return ""

    completed = subprocess.run(
        command,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=gphoto_environment(),
    )

    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise GPhotoError(f"Command failed: {printable}\n{detail}")

    return completed.stdout


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


def parse_camera_file(capture_output: str) -> tuple[str, str]:
    patterns = (
        r"New file is in location\s+(.+?)\s+on the camera",
        r"新文件在相机中\s+(.+?)\s+处",
    )
    camera_path = None

    for pattern in patterns:
        match = re.search(pattern, capture_output)
        if match:
            camera_path = match.group(1).strip()
            break

    if not camera_path:
        raise GPhotoError(f"Could not find captured camera file in gPhoto2 output:\n{capture_output}")

    if "/" not in camera_path:
        return "/", camera_path

    folder, filename = camera_path.rsplit("/", 1)
    return folder or "/", filename


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


def download_camera_file(
    gphoto: str,
    folder: str,
    camera_file: str,
    destination: Path,
    *,
    dry_run: bool,
) -> None:
    log(f"Downloading {folder}/{camera_file} to {destination}")
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


def camera_path(folder: str, camera_file: str) -> str:
    if folder == "/":
        return f"/{camera_file}"
    return f"{folder.rstrip('/')}/{camera_file}"


def download_camera_file_in_shell(
    shell: GPhotoShellSession,
    folder: str,
    camera_file: str,
    destination: Path,
) -> None:
    source = camera_path(folder, camera_file)
    temporary_file = shell.working_dir / Path(camera_file).name

    if temporary_file.exists():
        temporary_file.unlink()

    log(f"Downloading {source} to {destination}")
    shell.run(f"get {source}")

    if not temporary_file.exists():
        raise GPhotoError(f"Downloaded file was not found locally: {temporary_file}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_file.replace(destination)


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
        for index, ev in enumerate(BRACKET_STOPS, start=1):
            value = choice_for_ev(choices, ev)
            folder, camera_file = capture_to_camera(
                gphoto,
                exposure_config,
                value,
                ev,
                dry_run=dry_run,
            )
            captured_files.append((index, folder, camera_file))

        for index, folder, camera_file in captured_files:
            stem = f"{group:04d}_{index:02d}"
            destination = output_dir / f"{stem}.%C"
            download_camera_file(gphoto, folder, camera_file, destination, dry_run=dry_run)
    else:
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
                stem = f"{group:04d}_{index:02d}"
                suffix = Path(camera_file).suffix or ".jpg"
                destination = output_dir / f"{stem}{suffix}"
                download_camera_file_in_shell(shell, folder, camera_file, destination)

        try:
            download_temp_dir.rmdir()
        except OSError:
            pass

    elapsed = time.monotonic() - group_started
    log(
        f"Finished group {group:04d}; capture time: {elapsed:.1f} seconds; "
        f"started at {group_started_at}; finished at {current_timestamp()}"
    )


def build_parser() -> argparse.ArgumentParser:
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Capture +1 EV, 0 EV, and -1 EV photos through gPhoto2."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=script_dir / "capture",
        help="Download directory. Defaults to ./capture next to this script.",
    )
    parser.add_argument(
        "--config",
        help="gPhoto2 exposure compensation config path, if auto-detection fails.",
    )
    parser.add_argument(
        "--gphoto",
        default=shutil.which("gphoto2") or "gphoto2",
        help="Path to the gphoto2 executable.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print gPhoto2 commands without talking to a camera.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.dry_run and shutil.which(args.gphoto) is None and not Path(args.gphoto).exists():
        log(
            "gphoto2 was not found. Install gPhoto2 and make sure it is available in PATH, "
            "or pass --gphoto /path/to/gphoto2.",
            file=sys.stderr,
        )
        return 127

    try:
        exposure_config = find_exposure_config(args.gphoto, args.config, dry_run=args.dry_run)
        log(f"Using exposure compensation config: {exposure_config}")
        capture_bracket(
            args.gphoto,
            args.output_dir.resolve(),
            exposure_config,
            dry_run=args.dry_run,
        )
    except GPhotoError as exc:
        log(str(exc), file=sys.stderr)
        return 1

    log(f"Done. Files downloaded to: {args.output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
