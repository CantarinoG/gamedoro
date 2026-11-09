"""Play/block cycle state machine. Pure logic: no I/O, time is injected."""

from dataclasses import dataclass
from enum import Enum

# A tick longer than this (e.g. after suspend) is clamped so sleeping the
# laptop doesn't burn the play budget.
MAX_TICK = 5.0


class Phase(Enum):
    PLAYING = "playing"
    BLOCKED = "blocked"
    # Block time is over; games stay frozen until resume() is called.
    READY = "ready"


@dataclass
class Cycle:
    play_seconds: float
    block_seconds: float
    phase: Phase = Phase.PLAYING
    # Remaining play budget while PLAYING, remaining block time while BLOCKED
    # (0 while READY).
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
        elif self.phase is Phase.BLOCKED:
            self.remaining -= dt
            if self.remaining <= 0:
                self.phase = Phase.READY
                self.remaining = 0.0
                return self.phase
        return None  # READY just waits for resume()

    def resume(self) -> bool:
        """Leave READY and start a fresh play budget. False if not READY."""
        if self.phase is not Phase.READY:
            return False
        self.phase = Phase.PLAYING
        self.remaining = self.play_seconds
        return True
