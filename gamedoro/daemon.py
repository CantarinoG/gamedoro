"""Ties the cycle to the real world: detect games, freeze them, notify."""

import signal
import subprocess
import time
from pathlib import Path

from . import freezer, games, state
from .cycle import Cycle, Phase

# SIGHUP matters: closing the terminal the daemon runs in sends it, and dying
# without thawing would leave the game frozen.
STOP_SIGNALS = (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)
WARN_AT = 60.0  # seconds of play left when the warning goes out
SAVE_EVERY = 10.0  # seconds between state saves
CONFIG_EVERY = 5.0  # seconds between config file checks
# The overlay's clock runs a little past the daemon's, so that when it reads
# 00:00 the daemon is already waiting for Enter.
OVERLAY_MARGIN = 1.5
# While blocked we poll faster so the overlay follows workspace switches.
FAST_INTERVAL = 0.5
# A game's window can take a while to appear. Until it does we freeze nothing
# (so helpers aren't stopped needlessly); after this long we give up waiting
# and freeze the whole process tree instead.
WINDOW_GRACE = 15.0


def notify(title: str, body: str = "") -> None:
    try:
        subprocess.run(["notify-send", "-a", "gamedoro", title, body], timeout=5)
    except (OSError, subprocess.SubprocessError):
        pass  # notifications are best-effort


class Daemon:
    def __init__(self, cycle: Cycle, find=games.find_game_pids,
                 freeze=freezer.freeze, thaw=freezer.thaw, notify=notify,
                 state_path: Path | None = None, overlay=None,
                 clock=time.time, locate=None, watcher=None,
                 launch_bonus_seconds: float = 0.0,
                 pulse_every: float = 0.0, pulse_for: float = 0.0,
                 sleep=time.sleep):
        """`overlay` is optional; without one, blocks end by themselves.

        `locate(pids, app_ids)` returns a sway.GameView (the screens currently
        showing the game, empty if it's not on screen), or None if that can't be
        known, in which case the overlay covers every screen.

        `watcher` (a config.Watcher) is polled to pick up edited settings.

        Each time a game launches (none was running before), the play budget is
        topped up by `launch_bonus_seconds`, since loading isn't play time. A
        game that is already running when the daemon starts doesn't count.

        While frozen, the game is thawed for `pulse_for` seconds every
        `pulse_every` seconds (0 = never). A game that is stopped for minutes
        sees its clock jump in one frame and can come back stuck; pulsing keeps
        every stall short.
        """
        self.cycle = cycle
        self.state_path = state_path
        self._find, self._freeze, self._thaw, self._notify = find, freeze, thaw, notify
        self._overlay, self._clock, self._locate = overlay, clock, locate
        self._watcher = watcher
        self.launch_bonus_seconds = launch_bonus_seconds
        self.pulse_every, self.pulse_for, self._sleep = pulse_every, pulse_for, sleep
        self._since_pulse = 0.0
        self._had_game: bool | None = None  # None until the first look
        self._windowless = 0.0   # seconds a game has had no window yet
        self._fell_back = False  # froze the whole tree while waiting for a window
        self._frozen: set[int] = set()
        self._warned = False
        self._warned_overlay = False
        self._app_ids: set[str] = set()

    def step(self, dt: float) -> None:
        groups = self._find()
        pids = {pid for group in groups.values() for pid in group}
        self._app_ids = set(groups)
        launched = self._had_game is False and bool(pids)
        self._had_game = bool(pids)
        if launched and self.launch_bonus_seconds:
            self.cycle.launch_bonus(self.launch_bonus_seconds)
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
            self._step_ready(pids, dt)
        elif self.cycle.phase is Phase.BLOCKED:
            self._step_blocked(pids, dt)
        elif (not self._warned and pids
              and self.cycle.remaining <= WARN_AT < self.cycle.play_seconds):
            self._warned = True
            self._notify("1 minute of play left", "Save your game.")

    def _ui_wanted(self, pids) -> bool:
        """Show the overlay only if it works and there is a game to resume."""
        return self._overlay is not None and self._overlay.available and bool(pids)

    def _view(self, pids):
        """What sway says about the game, or None if we can't ask."""
        return self._locate(pids, self._app_ids) if self._locate else None

    def _targets(self, pids, view, dt: float) -> set[int]:
        """The processes to freeze.

        Just the one(s) owning the game's window, not the whole process tree:
        a Proton game's tree includes helpers like Social Club's embedded
        Chromium, whose watchdogs and network sessions don't survive a long
        stall, leaving the game hung on resume. Without sway we can't tell, so
        we freeze everything.
        """
        if view is None or not pids:
            self._windowless = 0.0
            return set(pids)
        if view.window_pids:
            self._windowless = 0.0
            return set(view.window_pids)
        self._windowless += dt
        if self._windowless > WINDOW_GRACE:
            self._fell_back = True
            return set(pids)
        return set()  # window not up yet; try again next tick

    def _hold(self, targets: set[int]) -> None:
        # Re-freeze every tick so games launched mid-block get caught too.
        if self._fell_back and targets and targets < self._frozen:
            # The window appeared after we froze everything: let the helpers go.
            self._thaw(self._frozen - targets)
            self._frozen &= targets
            self._fell_back = False
        self._freeze(targets)
        self._frozen |= targets

    def _maybe_pulse(self, dt: float) -> None:
        """Briefly let the frozen game run, so no single stall gets long."""
        if not self.pulse_every or not self._frozen:
            self._since_pulse = 0.0
            return
        self._since_pulse += dt
        if self._since_pulse < self.pulse_every:
            return
        self._since_pulse = 0.0
        self._thaw(self._frozen)
        self._sleep(self.pulse_for)
        self._freeze(self._frozen)

    def _step_blocked(self, pids, dt: float) -> None:
        view = self._view(pids)
        self._hold(self._targets(pids, view, dt))
        self._maybe_pulse(dt)
        if self._overlay is None:
            return
        if pids:
            until = self._clock() + self.cycle.remaining + OVERLAY_MARGIN
            self._show_overlay(view, until)
            self._overlay.confirmed()  # Enter pressed early doesn't count
        else:
            self._overlay.hide()  # game quit: don't blank the desktop for nothing

    def _step_ready(self, pids, dt: float) -> None:
        if self._ui_wanted(pids):
            view = self._view(pids)
            self._hold(self._targets(pids, view, dt))
            self._maybe_pulse(dt)
            self._show_overlay(view, self._clock())
            if not self._overlay.confirmed() and self._overlay.available:
                return  # keep waiting for Enter
        self.resume()  # confirmed, or there is nothing (or no way) to wait on

    def _show_overlay(self, view, until: float) -> None:
        """Cover the screen(s) showing the game; nothing if you're elsewhere."""
        areas = None if view is None else view.areas
        if areas is not None and not areas:
            self._overlay.hide()  # game isn't on screen: leave the user alone
        else:
            self._overlay.show(until, areas)

    def interval(self, slow: float = 1.0) -> float:
        """Seconds to sleep between steps."""
        waiting = self.cycle.phase is not Phase.PLAYING and self._overlay is not None
        return FAST_INTERVAL if waiting else slow

    def reload_config(self) -> None:
        """Apply edited settings. They take effect from the next cycle: a block
        or play budget already running keeps the length it started with, so
        editing the file can't shorten a block you're in."""
        if self._watcher is None:
            return
        new, error = self._watcher.poll()
        if error:
            self._notify("gamedoro: bad config", f"{error}\nKeeping the old settings.")
        elif new is not None:
            self.cycle.play_seconds = new.play * 60
            self.cycle.block_seconds = new.block * 60
            self.launch_bonus_seconds = new.launch_bonus * 60
            self.pulse_every, self.pulse_for = new.pulse_every_seconds, new.pulse_for_seconds
            self._notify("gamedoro: settings reloaded",
                         f"play {new.play:g} min, block {new.block:g} min "
                         "(from the next cycle)")

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
        self._since_pulse = 0.0

    def save(self) -> None:
        if self.state_path is not None:
            try:
                state.save(self.cycle, self.state_path)
            except OSError:
                pass  # losing a save is better than crashing mid-block

    def run(self) -> None:
        def stop(*_):
            raise SystemExit(0)
        for sig in STOP_SIGNALS:
            signal.signal(sig, stop)
        if self.cycle.phase is Phase.PLAYING:
            # A previous run may have died (SIGKILL) mid-block, leaving games frozen.
            self._thaw({pid for g in self._find().values() for pid in g})
        last = last_save = last_config = time.monotonic()
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
                if now - last_config >= CONFIG_EVERY:
                    self.reload_config()
                    last_config = now
        finally:
            self.release()
            self.save()
