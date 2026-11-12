"""Play a short sound, fire and forget, using whichever player is installed."""

import shutil
import subprocess
from pathlib import Path

SOUND_DIR = Path("/usr/share/sounds/freedesktop/stereo")
DEFAULTS = ("alarm-clock-elapsed.oga", "complete.oga", "bell.oga")
# Players that exit by themselves once the file is done.
PLAYERS = (["pw-play"], ["paplay"],
           ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"])

_pending: list = []  # players we haven't reaped yet


def resolve(setting: str, sound_dir: Path = SOUND_DIR) -> Path | None:
    """The file `setting` stands for: "" is none, "default" is a stock
    freedesktop sound (None if the system has none), anything else a path."""
    if not setting:
        return None
    if setting == "default":
        return next((sound_dir / n for n in DEFAULTS if (sound_dir / n).exists()), None)
    return Path(setting).expanduser()


def play(setting: str, which=shutil.which, spawn=subprocess.Popen,
         sound_dir: Path = SOUND_DIR) -> bool:
    """Start playing; True if a player was launched. Never raises or waits."""
    path = resolve(setting, sound_dir)
    if path is None or not path.exists():
        return False
    for proc in _pending[:]:
        if proc.poll() is not None:
            _pending.remove(proc)
    for command in PLAYERS:
        if which(command[0]):
            try:
                _pending.append(spawn(command + [str(path)], stdin=subprocess.DEVNULL,
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
                return True
            except OSError:
                continue
    return False
