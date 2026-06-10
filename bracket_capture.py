#!/usr/bin/env python3
"""
Capture a three-shot exposure bracket with gPhoto2.

The script sets exposure compensation to +1 EV, 0 EV, and -1 EV, captures one
image at each setting, and downloads the files into ./capture next to this file.
"""

from __future__ import annotations

import argparse
import datetime as dt
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


class GPhotoError(RuntimeError):
    """Raised when a gPhoto2 command fails or camera settings are unsupported."""


def current_timestamp() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(message: str, *, file=None) -> None:
    if file is None:
        file = sys.stdout
    print(f"[{current_timestamp()}] {message}", file=file)


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

    for index, ev in enumerate(BRACKET_STOPS, start=1):
        value = choice_for_ev(choices, ev)
        stem = f"{group:04d}_{index:02d}"
        filename = str(output_dir / f"{stem}.%C")

        log(f"Setting exposure compensation to {format_ev(ev)} EV")
        run_gphoto(gphoto, ["--set-config", f"{exposure_config}={value}"], dry_run=dry_run)

        log(f"Capturing {filename}")
        run_gphoto(
            gphoto,
            [
                "--capture-image-and-download",
                "--filename",
                filename,
                "--force-overwrite",
            ],
            dry_run=dry_run,
        )

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
