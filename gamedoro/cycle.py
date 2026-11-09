"""Play/block cycle state machine. Pure logic: no I/O, time is injected."""

from dataclasses import dataclass
from enum import Enum

# A tick longer than this (e.g. after suspend) is clamped so sleeping the
# laptop doesn't burn the play budget.
MAX_TICK = 5.0


class Phase(Enum):
    PLAYING = "playing"
    BLOCKED = "blocked"


@dataclass
class Cycle:
    play_seconds: float
    block_seconds: float
    phase: Phase = Phase.PLAYING
    # Remaining play budget while PLAYING, remaining block time while BLOCKED.
    remaining: float = 0.0
    # Extra play time for the first cycle only (games take a while to load).
    first_bonus_seconds: float = 0.0

    def __post_init__(self):
        if self.remaining == 0.0:
            self.remaining = self.play_seconds + self.first_bonus_seconds

    def tick(self, dt: float, game_running: bool) -> Phase | None:
        """Advance by dt seconds. Returns the new phase if it changed."""
        dt = min(max(dt, 0.0), MAX_TICK)
        if self.phase is Phase.PLAYING:
            if not game_running:
                return None  # budget only drains while a game is running
            self.remaining -= dt
            if self.remaining <= 0:
                self.phase = Phase.BLOCKED
                self.remaining = self.block_seconds
                return self.phase
        else:
            self.remaining -= dt
            if self.remaining <= 0:
                self.phase = Phase.PLAYING
                self.remaining = self.play_seconds
                return self.phase
        return None
