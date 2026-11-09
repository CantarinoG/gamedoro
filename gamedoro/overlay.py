"""Manage the overlay process: a fullscreen terminal running overlay_ui."""

import os
import shlex
import subprocess
import sys
import tempfile
import time
from pathlib import Path

UI_SCRIPT = Path(__file__).with_name("overlay_ui.py")
# Whatever follows this command is run as the program inside the terminal.
DEFAULT_TERMINAL = "foot --fullscreen --app-id gamedoro-overlay"


def default_confirm_file() -> Path:
    base = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
    return Path(base) / "gamedoro" / "confirmed"


class Overlay:
    def __init__(self, terminal: str = DEFAULT_TERMINAL,
                 confirm_file: Path | None = None,
                 spawn=subprocess.Popen, clock=time.time,
                 retry_after: float = 2.0):
        self.terminal = shlex.split(terminal)
        self.confirm_file = confirm_file or default_confirm_file()
        self._spawn, self._clock, self._retry_after = spawn, clock, retry_after
        self._proc = None
        self._last_spawn = float("-inf")
        # Turns False if the terminal can't be launched at all.
        self.available = True

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def show(self, until: float) -> None:
        """Make sure the overlay is up, counting down to `until` (epoch).

        If the user closes it, it is brought back (at most every retry_after
        seconds, so a broken terminal can't cause a spawn storm).
        """
        now = self._clock()
        if not self.available or self.running or now - self._last_spawn < self._retry_after:
            return
        self._last_spawn = now
        self.confirm_file.parent.mkdir(parents=True, exist_ok=True)
        cmd = [*self.terminal, sys.executable, str(UI_SCRIPT),
               "--until", str(until), "--confirm-file", str(self.confirm_file)]
        try:
            self._proc = self._spawn(cmd, stdin=subprocess.DEVNULL)
        except OSError:
            self.available = False

    def hide(self) -> None:
        if self.running:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait()
        self._proc = None

    def confirmed(self) -> bool:
        """True once, if the user pressed Enter at the prompt."""
        try:
            self.confirm_file.unlink()
        except FileNotFoundError:
            return False
        return True
