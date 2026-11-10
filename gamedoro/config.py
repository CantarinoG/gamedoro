"""Settings: built-in defaults < config file < command-line flags."""

import os
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Settings:
    play: float = 50.0        # minutes of play per cycle
    block: float = 10.0       # minutes games stay frozen
    launch_bonus: float = 10.0  # extra minutes whenever a game launches (loading)
    overlay: bool = True      # show the countdown / wait for Enter
    # While a game is frozen, thaw it for pulse_for_seconds every
    # pulse_every_seconds so no single stall is long (0 = never pulse).
    pulse_every_seconds: float = 30.0
    pulse_for_seconds: float = 1.0
    # Key pressed in the game (if it has focus) just before freezing it, to use
    # the game's own pause. An X keysym name like "Escape"; "" turns it off.
    pause_key: str = "Escape"
    pause_wait_seconds: float = 1.5  # give the game this long to pause first

    def validate(self) -> "Settings":
        if self.play <= 0 or self.block <= 0:
            raise ConfigError("play and block must be positive")
        if self.launch_bonus < 0:
            raise ConfigError("launch_bonus can't be negative")
        if self.pause_wait_seconds < 0:
            raise ConfigError("pause_wait_seconds can't be negative")
        if self.pulse_every_seconds < 0:
            raise ConfigError("pulse_every_seconds can't be negative")
        if self.pulse_every_seconds > 0 and not (
                0 < self.pulse_for_seconds < self.pulse_every_seconds):
            raise ConfigError("pulse_for_seconds must be above 0 and below "
                              "pulse_every_seconds (or set pulse_every_seconds = 0)")
        return self


FIELDS = {"play": float, "block": float, "launch_bonus": float, "overlay": bool,
          "pulse_every_seconds": float, "pulse_for_seconds": float,
          "pause_key": str, "pause_wait_seconds": float}
# Old names still accepted in the config file. first_bonus used to be a one-off
# bonus for the first cycle; it now means the same as launch_bonus.
ALIASES = {"first_bonus": "launch_bonus"}


def default_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "gamedoro" / "config.toml"


def read_file(path: Path) -> dict:
    """Values set in the config file. A missing file is fine; a bad one isn't."""
    try:
        raw = tomllib.loads(path.read_text())
    except FileNotFoundError:
        return {}
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise ConfigError(f"{path}: {e}") from e
    for old, new in ALIASES.items():
        if old in raw:
            if new in raw:
                raise ConfigError(f"{path}: set {new}, not both {new} and {old}")
            raw[new] = raw.pop(old)
    unknown = set(raw) - set(FIELDS)
    if unknown:
        raise ConfigError(f"{path}: unknown setting(s) {', '.join(sorted(unknown))} "
                          f"(valid: {', '.join(FIELDS)})")
    values = {}
    for key, value in raw.items():
        kind = FIELDS[key]
        if kind is bool:
            ok = isinstance(value, bool)
        elif kind is str:
            ok = isinstance(value, str)
        else:  # numbers: accept ints too, but not bools
            ok = isinstance(value, (int, float)) and not isinstance(value, bool)
        if not ok:
            raise ConfigError(f"{path}: {key} must be a "
                              f"{ {bool: 'true/false value', str: 'string'}.get(kind, 'number') }")
        values[key] = kind(value)
    return values


def resolve(path: Path, overrides: dict | None = None) -> Settings:
    """Defaults, then the file, then `overrides` (explicit CLI flags)."""
    settings = replace(Settings(), **read_file(path))
    settings = replace(settings, **{k: v for k, v in (overrides or {}).items()
                                    if v is not None})
    return settings.validate()


class Watcher:
    """Notices edits to the config file while the daemon runs."""

    def __init__(self, path: Path, overrides: dict | None = None):
        self.path, self.overrides = path, overrides
        self._seen = self._stamp()

    def _stamp(self):
        try:
            st = self.path.stat()
        except OSError:
            return None
        return (st.st_mtime_ns, st.st_size)

    def poll(self) -> tuple[Settings | None, str | None]:
        """(new settings, None) after a good edit, (None, message) after a bad
        one, (None, None) if nothing changed. A bad edit is reported once."""
        stamp = self._stamp()
        if stamp == self._seen:
            return None, None
        self._seen = stamp
        try:
            return resolve(self.path, self.overrides), None
        except ConfigError as e:
            return None, str(e)
