"""Ask sway where game windows are, so the overlay only covers the right screen.

A layer-shell overlay belongs to a monitor, not a workspace, so without this it
would stay up after you switch away from the frozen game.
"""

import json
import subprocess
from dataclasses import dataclass, field

from .env import session_env

Area = tuple[int, int, int, int]  # x, y, width, height of an output


@dataclass
class GameView:
    """What sway knows about a game right now."""
    areas: set[Area] = field(default_factory=set)       # screens showing it
    window_pids: set[int] = field(default_factory=set)  # processes owning its main window(s)


def game_view(tree: dict, pids: set[int], app_ids: set[str]) -> GameView:
    """Where a game's windows are, and which processes own them.

    A window belongs to the game if its pid is one of the game's pids or its
    class/app_id is steam_app_<id> (Proton).

    areas: outputs on which such a window is visible. `visible` is sway's own
    flag, so a game on another workspace, or hidden behind a fullscreen window,
    doesn't count.

    window_pids: the pids owning the game's main window(s), whether visible or
    not. Small helper windows (under half the size of the biggest) are ignored,
    and only pids that really belong to the game are returned. Freezing just
    these, rather than the whole process tree, leaves helpers like Social Club's
    embedded browser running, so they don't wake up to a long stall.
    """
    classes = {f"steam_app_{a}" for a in app_ids}
    areas: set[Area] = set()
    windows: list[tuple[int, int]] = []  # (area in pixels, pid)

    def walk(node: dict, area: Area | None) -> None:
        if node.get("type") == "output":
            r = node["rect"]
            area = (r["x"], r["y"], r["width"], r["height"])
        props = node.get("window_properties") or {}
        name = node.get("app_id") or props.get("class")
        is_window = node.get("pid") and not node.get("nodes")
        if is_window and (node["pid"] in pids or name in classes):
            r = node["rect"]
            windows.append((r["width"] * r["height"], node["pid"]))
            if area and node.get("visible"):
                areas.add(area)
        for child in node.get("nodes", []) + node.get("floating_nodes", []):
            walk(child, area)

    walk(tree, None)
    biggest = max((a for a, _ in windows), default=0)
    owners = {pid for a, pid in windows if a * 2 >= biggest and pid in pids}
    return GameView(areas, owners)


def query_game_view(pids: set[int], app_ids: set[str],
                    run=subprocess.run) -> GameView | None:
    """game_view() for the live sway, or None if sway can't be asked."""
    try:
        out = run(["swaymsg", "-t", "get_tree"], capture_output=True,
                  timeout=2, check=True, env=session_env()).stdout
        return game_view(json.loads(out), pids, app_ids)
    except (OSError, subprocess.SubprocessError, ValueError, KeyError):
        return None
