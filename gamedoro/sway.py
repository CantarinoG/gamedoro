"""Ask sway where game windows are, so the overlay only covers the right screen.

A layer-shell overlay belongs to a monitor, not a workspace, so without this it
would stay up after you switch away from the frozen game.
"""

import json
import subprocess

from .env import session_env

Area = tuple[int, int, int, int]  # x, y, width, height of an output


def game_areas(tree: dict, pids: set[int], app_ids: set[str]) -> set[Area]:
    """Outputs on which a window of the given game is currently visible.

    A window belongs to the game if its pid is one of the game's pids or its
    class/app_id is steam_app_<id> (Proton). `visible` is sway's own flag, so a
    game on another workspace, or hidden behind a fullscreen window, doesn't count.
    """
    classes = {f"steam_app_{a}" for a in app_ids}
    found: set[Area] = set()

    def walk(node: dict, area: Area | None) -> None:
        if node.get("type") == "output":
            r = node["rect"]
            area = (r["x"], r["y"], r["width"], r["height"])
        props = node.get("window_properties") or {}
        name = node.get("app_id") or props.get("class")
        is_window = node.get("pid") and not node.get("nodes")
        if (area and is_window and node.get("visible")
                and (node["pid"] in pids or name in classes)):
            found.add(area)
        for child in node.get("nodes", []) + node.get("floating_nodes", []):
            walk(child, area)

    walk(tree, None)
    return found


def query_game_areas(pids: set[int], app_ids: set[str],
                     run=subprocess.run) -> set[Area] | None:
    """game_areas() for the live sway, or None if sway can't be asked."""
    try:
        out = run(["swaymsg", "-t", "get_tree"], capture_output=True,
                  timeout=2, check=True, env=session_env()).stdout
        return game_areas(json.loads(out), pids, app_ids)
    except (OSError, subprocess.SubprocessError, ValueError, KeyError):
        return None
