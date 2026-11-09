"""Ties the cycle to the real world: detect games, freeze them, notify."""

import signal
import subprocess
import time
from pathlib import Path

from . import freezer, games, state
from .cycle import Cycle, Phase

WARN_AT = 60.0  # seconds of play left when the warning goes out
SAVE_EVERY = 10.0  # seconds between state saves
# The overlay's clock runs a little past the daemon's, so that when it reads
# 00:00 the daemon is already waiting for Enter.
OVERLAY_MARGIN = 1.5
# While blocked we poll faster so the overlay follows workspace switches.
FAST_INTERVAL = 0.5


def notify(title: str, body: str = "") -> None:
    try:
        subprocess.run(["notify-send", "-a", "gamedoro", title, body], timeout=5)
    except (OSError, subprocess.SubprocessError):
        pass  # notifications are best-effort


class Daemon:
    def __init__(self, cycle: Cycle, find=games.find_game_pids,
                 freeze=freezer.freeze, thaw=freezer.thaw, notify=notify,
                 state_path: Path | None = None, overlay=None,
                 clock=time.time, locate=None):
        """`overlay` is optional; without one, blocks end by themselves.

        `locate(pids, app_ids)` returns the screens currently showing the game
        (an empty set if it's not on screen), or None if that can't be known,
        in which case the overlay covers every screen.
        """
        self.cycle = cycle
        self.state_path = state_path
        self._find, self._freeze, self._thaw, self._notify = find, freeze, thaw, notify
        self._overlay, self._clock, self._locate = overlay, clock, locate
        self._frozen: set[int] = set()
        self._warned = False
        self._warned_overlay = False
        self._app_ids: set[str] = set()

    def step(self, dt: float) -> None:
        groups = self._find()
        pids = {pid for group in groups.values() for pid in group}
        self._app_ids = set(groups)
        changed = self.cycle.tick(dt, game_running=bool(pids))

        if changed is Phase.BLOCKED:
            self._warned = False
            self._notify("Time's up!", f"Games frozen for {self.cycle.block_seconds / 60:g} min.")
        elif changed is Phase.READY and self._ui_wanted(pids):
            self._notify("Block over", "Press Enter on the overlay to resume.")

        if (self._overlay is not None and not self._overlay.available
                and not self._warned_overlay):
            self._warned_overlay = True
            self._notify("Overlay unavailable", "Blocks will end without waiting for Enter.")

        if self.cycle.phase is Phase.READY:
            self._step_ready(pids)
        elif self.cycle.phase is Phase.BLOCKED:
            self._step_blocked(pids)
        elif (not self._warned and pids
              and self.cycle.remaining <= WARN_AT < self.cycle.play_seconds):
            self._warned = True
            self._notify("1 minute of play left", "Save your game.")

    def _ui_wanted(self, pids) -> bool:
        """Show the overlay only if it works and there is a game to resume."""
        return self._overlay is not None and self._overlay.available and bool(pids)

    def _hold(self, pids) -> None:
        # Re-freeze every tick so games launched mid-block get caught too.
        self._freeze(pids)
        self._frozen |= pids

    def _step_blocked(self, pids) -> None:
        self._hold(pids)
        if self._overlay is None:
            return
        if pids:
            until = self._clock() + self.cycle.remaining + OVERLAY_MARGIN
            self._show_overlay(pids, until)
            self._overlay.confirmed()  # Enter pressed early doesn't count
        else:
            self._overlay.hide()  # game quit: don't blank the desktop for nothing

    def _step_ready(self, pids) -> None:
        if self._ui_wanted(pids):
            self._hold(pids)
            self._show_overlay(pids, self._clock())
            if not self._overlay.confirmed() and self._overlay.available:
                return  # keep waiting for Enter
        self.resume()  # confirmed, or there is nothing (or no way) to wait on

    def _show_overlay(self, pids, until: float) -> None:
        """Cover the screen(s) showing the game; nothing if you're elsewhere."""
        areas = self._locate(pids, self._app_ids) if self._locate else None
        if areas is not None and not areas:
            self._overlay.hide()  # game isn't on screen: leave the user alone
        else:
            self._overlay.show(until, areas)

    def interval(self, slow: float = 1.0) -> float:
        """Seconds to sleep between steps."""
        waiting = self.cycle.phase is not Phase.PLAYING and self._overlay is not None
        return FAST_INTERVAL if waiting else slow

    def resume(self) -> None:
        """End a finished block: thaw the games and start a new play cycle."""
        if self.cycle.resume():
            self.release()
            self._notify("Block over", "Games resumed. Have fun!")

    def release(self) -> None:
        """Thaw everything we froze and drop the overlay. Runs on every exit path."""
        if self._overlay is not None:
            self._overlay.hide()
        self._thaw(self._frozen)
        self._frozen.clear()

    def save(self) -> None:
        if self.state_path is not None:
            try:
                state.save(self.cycle, self.state_path)
            except OSError:
                pass  # losing a save is better than crashing mid-block

    def run(self) -> None:
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
                time.sleep(self.interval())
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
