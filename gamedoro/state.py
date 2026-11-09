"""Persist the cycle so restarting the daemon doesn't reset a block."""

import json
import os
import time
from pathlib import Path

from .cycle import Cycle, Phase


def default_path() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state"
    return Path(base) / "gamedoro" / "state.json"


def save(cycle: Cycle, path: Path, now: float | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({
        "phase": cycle.phase.value,
        "remaining": cycle.remaining,
        "saved_at": time.time() if now is None else now,
    }))
    tmp.replace(path)  # atomic: never a half-written file


def load(play_seconds: float, block_seconds: float, path: Path,
         now: float | None = None, first_bonus_seconds: float = 0.0) -> Cycle:
    """Restore a cycle, or start fresh if there is no usable saved state.

    A running block keeps counting down in wall-clock time while the daemon is
    off, so restarting it is not a way out. Play budget is restored as-is; the
    first-cycle bonus only applies when there is no saved state to restore.
    """
    cycle = Cycle(play_seconds, block_seconds, first_bonus_seconds=first_bonus_seconds)
    try:
        data = json.loads(path.read_text())
        phase, remaining = Phase(data["phase"]), float(data["remaining"])
        saved_at = float(data["saved_at"])
    except (OSError, ValueError, KeyError, TypeError):
        return cycle
    if phase is Phase.BLOCKED:
        remaining -= (time.time() if now is None else now) - saved_at
        if remaining > 0:
            cycle.phase, cycle.remaining = Phase.BLOCKED, min(remaining, block_seconds)
    elif 0 < remaining <= play_seconds + first_bonus_seconds:
        cycle.remaining = remaining
    return cycle
