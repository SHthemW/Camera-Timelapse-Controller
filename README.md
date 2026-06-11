# Camera Timelapse Controller

English | [简体中文](README.zh-CN.md)

Camera Timelapse Controller is a small Python command-line tool for running
bracketed timelapse capture through `gphoto2`.

It is designed for cameras that can capture to camera storage and then download
the captured files back to the computer. The default mode uses the camera's AEB
state to finish each 3-shot bracket group, while manual mode changes exposure
compensation for each shot.

## Features

- Capture repeated 3-shot bracket groups for timelapse workflows.
- Use camera AEB mode by default.
- Use manual exposure compensation when AEB is not suitable.
- Download files into a numbered output sequence.
- Remove captured files from camera storage after download.
- Continue numbering from existing files in the output directory.
- Keep round intervals based on timestamps, so capture and download time counts
  toward `--interval`.
- Warn and start the next round immediately when a round takes longer than the
  configured interval.
- Suppress macOS `PTPCamera` while the capture session is running.
- Provide `--dry-run` for command preview and flow checks.

## Requirements

- Python 3.9 or newer is recommended.
- `gphoto2` must be installed and able to access your camera.
- A camera supported by `gphoto2`.

On macOS, install `gphoto2` with Homebrew:

```bash
brew install gphoto2
```

Check that the camera is visible:

```bash
gphoto2 --auto-detect
```

## Quick Start

Install the command in editable mode from the project directory:

```bash
python3 -m pip install -e .
```

If your system pip is old, run this inside a virtual environment after upgrading
`pip`, `setuptools`, and `wheel`.

Capture two bracket rounds with a 5-second interval between round starts:

```bash
camera-timelapse . --interval 5 --round 2
```

Capture forever until interrupted:

```bash
camera-timelapse . --interval 10
```

Wait until 2026-06-12 21:30 before starting capture:

```bash
camera-timelapse --start-at 21:30 --start-day 2026-06-12 --interval 5 --round 100
```

If `--start-day` is omitted, the program uses today's date.

Stop after the current group once 2026-06-12 22:00 is reached:

```bash
camera-timelapse --end-at 22:00 --end-day 2026-06-12 --interval 5
```

If `--round` is also set, `--round` wins and `--end-at/--end-day` are ignored with a warning.
If `--end-day` is omitted, the program uses `--start-day`, or today's date if `--start-day` is also omitted.

Write files to a custom directory:

```bash
camera-timelapse ./capture --interval 6 --round 100
```

Preview the flow without talking to a camera:

```bash
camera-timelapse . --dry-run --interval 5 --round 2
```

The legacy script entry point still works:

```bash
python3 /path/to/Camera-Timelapse-Controller/bracket_capture.py . --interval 5 --round 2
```

If you omit the directory, the program asks for it at runtime.

## Capture Modes

### AEB Mode

AEB mode is the default:

```bash
camera-timelapse . --mode aeb --interval 5 --round 10
```

The tool reads the camera's current AEB shot index and finishes the current
3-shot bracket group. If the camera is already in the middle of an AEB group,
the tool captures only the shots needed to complete that group.

### Manual Mode

Manual mode changes exposure compensation before each shot:

```bash
camera-timelapse . --mode manual --interval 5 --round 10
```

If the exposure compensation setting cannot be detected automatically, pass it
explicitly:

```bash
camera-timelapse . --mode manual --config /main/capturesettings/exposurecompensation
```

You can inspect supported camera config paths with:

```bash
gphoto2 --list-config
```

## Interval Behavior

`--interval` is the target time between capture round starts.

For example, if `--interval 6` is set and capture plus download takes 3 seconds,
the tool waits 3 more seconds before starting the next round.

If capture plus download takes longer than the configured interval, the tool logs
a warning and starts the next round immediately.

Use `--interval 0` to disable delay between rounds.

## Output Files

Files are written to the directory you pass in, or the directory you enter at
the prompt, and named as a numbered sequence:

```text
0001_01.jpg
0001_02.jpg
0001_03.jpg
0002_01.jpg
0002_02.jpg
0002_03.jpg
```

If the output directory already contains numbered files, the next group number
continues from the highest existing group.

Files are downloaded directly into the chosen directory.
After each successful download, the camera copy is deleted.

If the session is interrupted, already completed files stay in that directory,
and a partially downloaded current file may remain with its camera name.

## Command Reference

```text
--mode {aeb,manual}       Capture mode. Defaults to aeb.
output_dir PATH           Download directory. Example: .
--output-dir PATH         Optional alias for the same directory.
--config PATH             Exposure compensation config path for manual mode.
--gphoto PATH             Path to the gphoto2 executable.
--dry-run                 Print commands without controlling a camera.
--interval SECONDS        Seconds between capture round starts.
--start-at HH:MM          Wait until the scheduled 24-hour start time.
--start-day YYYY-MM-DD    Date for --start-at. Defaults to today.
--end-at HH:MM            Stop after the current group once the scheduled time is reached.
--end-day YYYY-MM-DD      Date for --end-at. Defaults to --start-day or today.
--round COUNT             Total capture rounds. Omit to capture forever.
```

## Notes

- Configure camera AEB settings on the camera before using AEB mode.
- Make sure the camera storage has enough space for the session.
- Make sure the computer has enough free disk space for downloaded files.
- Captured files are removed from camera storage after they are downloaded.
- Press `Ctrl-C` to stop a running session.
