"""Manage the overlay process (overlay_ui.py) shown while games are frozen."""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

UI_SCRIPT = Path(__file__).with_name("overlay_ui.py")
# An overlay that dies this soon after launch never really appeared (e.g. no
# Wayland display). After MAX_QUICK_DEATHS in a row we stop trying.
QUICK_DEATH = 3.0
MAX_QUICK_DEATHS = 3


def default_confirm_file() -> Path:
    base = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
    return Path(base) / "gamedoro" / "confirmed"


class Overlay:
    def __init__(self, confirm_file: Path | None = None,
                 spawn=subprocess.Popen, clock=time.time,
                 retry_after: float = 2.0):
        self.confirm_file = confirm_file or default_confirm_file()
        self._spawn, self._clock, self._retry_after = spawn, clock, retry_after
        self._proc = None
        self._last_spawn = float("-inf")
        self._quick_deaths = 0
        # Turns False if the overlay can't be launched at all.
        self.available = True

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def show(self, until: float) -> None:
        """Make sure the overlay is up, counting down to `until` (epoch).

        If the user closes it, it is brought back (at most every retry_after
        seconds, so a broken overlay can't cause a spawn storm).
        """
        now = self._clock()
        self._account_for_exit(now)
        if not self.available or self.running or now - self._last_spawn < self._retry_after:
            return
        self._last_spawn = now
        self.confirm_file.parent.mkdir(parents=True, exist_ok=True)
        cmd = [sys.executable, str(UI_SCRIPT),
               "--until", str(until), "--confirm-file", str(self.confirm_file)]
        try:
            self._proc = self._spawn(cmd, stdin=subprocess.DEVNULL)
        except OSError:
            self.available = False

    def _account_for_exit(self, now: float) -> None:
        """Notice an overlay that exited on its own, and count instant failures."""
        if self._proc is None or self.running:
            return
        self._proc = None
        if now - self._last_spawn < QUICK_DEATH:
            self._quick_deaths += 1
            if self._quick_deaths >= MAX_QUICK_DEATHS:
                self.available = False
        else:
            self._quick_deaths = 0

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
