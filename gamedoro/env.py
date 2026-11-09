"""Find the Wayland/sway sockets when we weren't started from the session.

A systemd user service starts without WAYLAND_DISPLAY and SWAYSOCK, and the
overlay and the sway query need both. The sockets live in the runtime dir, so
we can find them ourselves, with no changes to your sway config.
"""

import os
from pathlib import Path


def session_env(base=None, runtime_dir: Path | None = None) -> dict:
    """A copy of the environment with WAYLAND_DISPLAY / SWAYSOCK filled in.

    Anything already set is left alone. Looked up on every call, so a sway
    restart (new sockets) is picked up.
    """
    env = dict(os.environ if base is None else base)
    runtime = runtime_dir or Path(env.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}")
    env.setdefault("XDG_RUNTIME_DIR", str(runtime))
    if not env.get("WAYLAND_DISPLAY"):
        sockets = sorted(p.name for p in runtime.glob("wayland-*")
                         if not p.name.endswith(".lock"))
        if sockets:
            env["WAYLAND_DISPLAY"] = sockets[0]
    if not env.get("SWAYSOCK"):
        # Newest first: a restarted sway leaves a fresh socket.
        socks = sorted(runtime.glob("sway-ipc.*.sock"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        if socks:
            env["SWAYSOCK"] = str(socks[0])
    return env
