"""Play for X minutes, then your Steam games are frozen for Y minutes."""

import argparse
import sys
from pathlib import Path

from . import config, state, sway
from .daemon import Daemon
from .overlay import Overlay
from .overlay_ui import supported


def main() -> None:
    ap = argparse.ArgumentParser(prog="gamedoro", description=__doc__)
    ap.add_argument("--config", type=Path, default=config.default_path(), metavar="FILE",
                    help="settings file (default: %(default)s)")
    ap.add_argument("--play", type=float, metavar="MIN",
                    help="minutes of play allowed per cycle (default: 50)")
    ap.add_argument("--block", type=float, metavar="MIN",
                    help="minutes games stay frozen (default: 10)")
    ap.add_argument("--first-bonus", type=float, metavar="MIN",
                    help="extra minutes added to the first play cycle, to cover "
                         "game loading (default: 10; 0 disables)")
    ap.add_argument("--no-overlay", dest="overlay", action="store_const", const=False,
                    help="no countdown screen; blocks end by themselves")
    args = ap.parse_args()

    # Only flags actually given override the config file.
    overrides = {"play": args.play, "block": args.block,
                 "first_bonus": args.first_bonus, "overlay": args.overlay}
    try:
        settings = config.resolve(args.config, overrides)
    except config.ConfigError as e:
        ap.error(str(e))

    overlay = None
    if settings.overlay:
        ok, reason = supported()
        if ok:
            overlay = Overlay()
        else:
            print(f"gamedoro: warning: overlay unavailable ({reason}); blocks will "
                  "end without waiting for Enter", file=sys.stderr)

    path = state.default_path()
    cycle = state.load(settings.play * 60, settings.block * 60, path,
                       first_bonus_seconds=settings.first_bonus * 60)
    Daemon(cycle, state_path=path, overlay=overlay, locate=sway.query_game_areas,
           watcher=config.Watcher(args.config, overrides)).run()


if __name__ == "__main__":
    main()
