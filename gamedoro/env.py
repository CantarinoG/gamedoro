"""Find the Wayland/sway sockets when we weren't started from the session.

A systemd user service starts without WAYLAND_DISPLAY and SWAYSOCK, and the
overlay and the sway query need both. The sockets live in the runtime dir, so
we can find them ourselves, with no changes to your sway config.
"""

import os
from pathlib import Path


def session_env(base=None, runtime_dir: Path | None = None,
                x11_dir: Path = Path("/tmp/.X11-unix")) -> dict:
    """A copy of the environment with WAYLAND_DISPLAY / SWAYSOCK / DISPLAY filled in.

    Values that are set and still point at a live socket are left alone. A
    stale one (SWAYSOCK includes sway's pid, so it goes bad when sway restarts)
    is replaced. Looked up on every call, so a restart is picked up.
    """
    env = dict(os.environ if base is None else base)
    runtime = runtime_dir or Path(env.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}")
    env.setdefault("XDG_RUNTIME_DIR", str(runtime))
    wayland = env.get("WAYLAND_DISPLAY")
    if not wayland or not (Path(wayland) if os.path.isabs(wayland) else runtime / wayland).exists():
        sockets = sorted(p.name for p in runtime.glob("wayland-*")
                         if not p.name.endswith(".lock"))
        if sockets:
            env["WAYLAND_DISPLAY"] = sockets[0]
        elif not wayland:
            env.pop("WAYLAND_DISPLAY", None)
    swaysock = env.get("SWAYSOCK")
    if not swaysock or not Path(swaysock).exists():
        # Newest first: a restarted sway leaves a fresh socket.
        socks = sorted(runtime.glob("sway-ipc.*.sock"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        if socks:
            env["SWAYSOCK"] = str(socks[0])
    if not env.get("DISPLAY"):
        displays = sorted(p.name for p in x11_dir.glob("X[0-9]*"))
        if displays:
            env["DISPLAY"] = ":" + displays[0][1:]
    return env
