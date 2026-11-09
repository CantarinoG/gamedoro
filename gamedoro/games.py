"""Find running Steam games by scanning /proc for SteamAppId.

Steam sets SteamAppId in the environment of a game's launch chain, and every
child (Proton, wineserver, the game itself) inherits it. That gives us the
whole process tree without relying on cgroups or window titles.
"""

import os
from pathlib import Path

# Steam's own helper processes must never be frozen.
IGNORED_COMM = {"steam", "steamwebhelper", "steamerrorreporter"}


def parse_app_id(environ: bytes) -> str | None:
    """Return the SteamAppId from a raw /proc/<pid>/environ, if a real game."""
    for entry in environ.split(b"\0"):
        if entry.startswith(b"SteamAppId="):
            app_id = entry.split(b"=", 1)[1].decode(errors="replace")
            return app_id if app_id and app_id != "0" else None
    return None


def find_game_pids(proc: Path = Path("/proc")) -> dict[str, list[int]]:
    """Map each running game's app id to the pids in its process tree."""
    games: dict[str, list[int]] = {}
    me = os.getpid()
    for entry in proc.iterdir():
        if not entry.name.isdigit() or int(entry.name) == me:
            continue
        try:
            app_id = parse_app_id((entry / "environ").read_bytes())
            if app_id is None:
                continue
            if (entry / "comm").read_text().strip() in IGNORED_COMM:
                continue
        except OSError:
            continue  # process exited, or not ours
        games.setdefault(app_id, []).append(int(entry.name))
    return {app_id: sorted(pids) for app_id, pids in games.items()}
