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
    first_bonus: float = 10.0  # extra minutes on the first cycle
    overlay: bool = True      # show the countdown / wait for Enter

    def validate(self) -> "Settings":
        if self.play <= 0 or self.block <= 0:
            raise ConfigError("play and block must be positive")
        if self.first_bonus < 0:
            raise ConfigError("first_bonus can't be negative")
        return self


FIELDS = {"play": float, "block": float, "first_bonus": float, "overlay": bool}


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
    unknown = set(raw) - set(FIELDS)
    if unknown:
        raise ConfigError(f"{path}: unknown setting(s) {', '.join(sorted(unknown))} "
                          f"(valid: {', '.join(FIELDS)})")
    values = {}
    for key, value in raw.items():
        kind = FIELDS[key]
        if kind is bool:
            ok = isinstance(value, bool)
        else:  # numbers: accept ints too, but not bools
            ok = isinstance(value, (int, float)) and not isinstance(value, bool)
        if not ok:
            raise ConfigError(f"{path}: {key} must be a "
                              f"{'true/false value' if kind is bool else 'number'}")
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
