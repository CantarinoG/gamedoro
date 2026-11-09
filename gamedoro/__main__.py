"""Play for X minutes, then your Steam games are frozen for Y minutes."""

import argparse
import sys
from pathlib import Path

from . import config, state, sway
from .daemon import Daemon
from .overlay import Overlay
from .overlay_ui import bindings_available


def build_overlay(enabled: bool, check=bindings_available):
    """The overlay manager, or None if disabled or its bindings are missing.

    Deliberately does NOT test for a live compositor: started as a service at
    login, the display may not exist yet, and giving up then would disable the
    overlay for good. The overlay process checks when it actually launches.
    """
    if not enabled:
        return None
    ok, reason = check()
    if not ok:
        print(f"gamedoro: warning: overlay unavailable ({reason}); blocks will "
              "end without waiting for Enter", file=sys.stderr)
        return None
    return Overlay()


def main() -> None:
    ap = argparse.ArgumentParser(prog="gamedoro", description=__doc__)
    ap.add_argument("--config", type=Path, default=config.default_path(), metavar="FILE",
                    help="settings file (default: %(default)s)")
    ap.add_argument("--play", type=float, metavar="MIN",
                    help="minutes of play allowed per cycle (default: 50)")
    ap.add_argument("--block", type=float, metavar="MIN",
                    help="minutes games stay frozen (default: 10)")
    ap.add_argument("--launch-bonus", "--first-bonus", dest="launch_bonus", type=float,
                    metavar="MIN",
                    help="extra play minutes each time a game launches, to cover "
                         "loading (default: 10; 0 disables; capped at play + bonus)")
    ap.add_argument("--no-overlay", dest="overlay", action="store_const", const=False,
                    help="no countdown screen; blocks end by themselves")
    args = ap.parse_args()

    # Only flags actually given override the config file.
    overrides = {"play": args.play, "block": args.block,
                 "launch_bonus": args.launch_bonus, "overlay": args.overlay}
    try:
        settings = config.resolve(args.config, overrides)
    except config.ConfigError as e:
        ap.error(str(e))

    overlay = build_overlay(settings.overlay)

    path = state.default_path()
    cycle = state.load(settings.play * 60, settings.block * 60, path,
                       launch_bonus_seconds=settings.launch_bonus * 60)
    Daemon(cycle, state_path=path, overlay=overlay, locate=sway.query_game_areas,
           watcher=config.Watcher(args.config, overrides),
           launch_bonus_seconds=settings.launch_bonus * 60).run()


if __name__ == "__main__":
    main()
