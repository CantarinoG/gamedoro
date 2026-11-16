"""Find running games by scanning /proc: Steam games by SteamAppId, and
anything else (emulators...) by program name.

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


def matching_program(entry: Path, programs: set[str]) -> str | None:
    """The configured program name this process is, by its executable's name
    (or its comm: AppImages often report a generic comm like "AppRun")."""
    names = {(entry / "comm").read_text().strip().lower()}
    try:
        names.add(Path(os.readlink(entry / "exe")).name.lower())
    except OSError:
        pass
    return next((name for name in sorted(names) if name in programs), None)


def find_game_pids(proc: Path = Path("/proc"),
                   programs=()) -> dict[str, list[int]]:
    """Map each running game to the pids in its process tree.

    Steam games are keyed by app id. Processes whose executable (or comm) is
    one of `programs`, e.g. "pcsx2-qt", are keyed "program:<name>".
    """
    wanted = {p.lower() for p in programs}
    games: dict[str, list[int]] = {}
    me = os.getpid()
    for entry in proc.iterdir():
        if not entry.name.isdigit() or int(entry.name) == me:
            continue
        try:
            app_id = parse_app_id((entry / "environ").read_bytes())
            if app_id is not None:
                if (entry / "comm").read_text().strip() in IGNORED_COMM:
                    continue
                key = app_id
            else:
                program = matching_program(entry, wanted) if wanted else None
                if program is None:
                    continue
                key = f"program:{program}"
        except OSError:
            continue  # process exited, or not ours
        games.setdefault(key, []).append(int(entry.name))
    return {key: sorted(pids) for key, pids in games.items()}
