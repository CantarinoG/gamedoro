"""Ties the cycle to the real world: detect games, freeze them, notify."""

import signal
import subprocess
import time

from pathlib import Path

from . import freezer, games, state
from .cycle import Cycle, Phase

WARN_AT = 60.0  # seconds of play left when the warning goes out
SAVE_EVERY = 10.0  # seconds between state saves


def notify(title: str, body: str = "") -> None:
    try:
        subprocess.run(["notify-send", "-a", "gamedoro", title, body], timeout=5)
    except (OSError, subprocess.SubprocessError):
        pass  # notifications are best-effort


class Daemon:
    def __init__(self, cycle: Cycle, find=games.find_game_pids,
                 freeze=freezer.freeze, thaw=freezer.thaw, notify=notify,
                 state_path: Path | None = None):
        self.cycle = cycle
        self.state_path = state_path
        self._find, self._freeze, self._thaw, self._notify = find, freeze, thaw, notify
        self._frozen: set[int] = set()
        self._warned = False

    def step(self, dt: float) -> None:
        pids = {pid for group in self._find().values() for pid in group}
        changed = self.cycle.tick(dt, game_running=bool(pids))

        if changed is Phase.BLOCKED:
            self._warned = False
            self._notify("Time's up!", f"Games frozen for {self.cycle.block_seconds / 60:g} min.")

        if self.cycle.phase is Phase.READY:
            self.resume()  # no confirmation UI yet: resume straight away
            return

        if self.cycle.phase is Phase.BLOCKED:
            # Re-freeze every tick so games launched mid-block get caught too.
            self._freeze(pids)
            self._frozen |= pids
        elif (self.cycle.phase is Phase.PLAYING and not self._warned and pids
              and self.cycle.remaining <= WARN_AT < self.cycle.play_seconds):
            self._warned = True
            self._notify("1 minute of play left", "Save your game.")

    def resume(self) -> None:
        """End a finished block: thaw the games and start a new play cycle."""
        if self.cycle.resume():
            self.release()
            self._notify("Block over", "Games resumed. Have fun!")

    def release(self) -> None:
        """Thaw everything we froze. Must run on every exit path."""
        self._thaw(self._frozen)
        self._frozen.clear()

    def save(self) -> None:
        if self.state_path is not None:
            try:
                state.save(self.cycle, self.state_path)
            except OSError:
                pass  # losing a save is better than crashing mid-block

    def run(self, interval: float = 1.0) -> None:
        def stop(*_):
            raise SystemExit(0)
        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        if self.cycle.phase is Phase.PLAYING:
            # A previous run may have died (SIGKILL) mid-block, leaving games frozen.
            self._thaw({pid for g in self._find().values() for pid in g})
        last = last_save = time.monotonic()
        try:
            while True:
                time.sleep(interval)
                now = time.monotonic()
                phase_before = self.cycle.phase
                self.step(now - last)
                last = now
                if self.cycle.phase is not phase_before or now - last_save >= SAVE_EVERY:
                    self.save()
                    last_save = now
        finally:
            self.release()
            self.save()
