from __future__ import annotations

import subprocess
import threading

from gphoto_timelapse.core.log import log


PTPCAMERAD_PROCESS = "ptpcamerad"
DEFAULT_POLL_INTERVAL = 1.0


class ProcessSuppressor:
    def __init__(self, process_name: str, *, poll_interval: float = DEFAULT_POLL_INTERVAL) -> None:
        self.process_name = process_name
        self.poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "ProcessSuppressor":
        self.start()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.stop()

    def start(self) -> None:
        if self._thread is not None:
            return

        self.terminate_if_running()
        self._thread = threading.Thread(
            target=self._watch,
            name=f"{self.process_name}-suppressor",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        if self._thread is None:
            return

        self._stop_event.set()
        self._thread.join(timeout=self.poll_interval + 0.5)
        self._thread = None

    def terminate_if_running(self) -> None:
        process_ids = find_process_ids(self.process_name)
        if not process_ids:
            return

        log(f"Terminating {self.process_name} process(es): {', '.join(process_ids)}")
        completed = subprocess.run(
            ["pkill", "-9", "-x", self.process_name],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if completed.returncode == 0:
            log(f"{self.process_name} terminated")
        elif completed.returncode == 1:
            log(f"{self.process_name} exited before termination")
        else:
            detail = completed.stderr.strip() or completed.stdout.strip()
            log(f"Could not terminate {self.process_name}: {detail}")

    def _watch(self) -> None:
        while not self._stop_event.wait(self.poll_interval):
            self.terminate_if_running()


def find_process_ids(process_name: str) -> list[str]:
    completed = subprocess.run(
        ["pgrep", "-x", process_name],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode == 1:
        return []
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        log(f"Could not inspect {process_name}: {detail}")
        return []

    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def suppress_ptpcamerad() -> ProcessSuppressor:
    return ProcessSuppressor(PTPCAMERAD_PROCESS)
