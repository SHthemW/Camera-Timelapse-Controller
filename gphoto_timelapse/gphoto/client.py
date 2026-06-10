from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from gphoto_timelapse.core.log import log


SHELL_PROMPT_PATTERN = re.compile(r"(?:^|\n)gphoto2: .*?> $", re.DOTALL)


class GPhotoError(RuntimeError):
    """Raised when a gPhoto2 command fails or camera settings are unsupported."""


class GPhotoShellSession:
    def __init__(self, gphoto: str, working_dir: Path, *, extra_args: list[str] | None = None) -> None:
        self.working_dir = working_dir
        command = [gphoto, *(extra_args or []), "--shell"]
        self.process = subprocess.Popen(
            command,
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
