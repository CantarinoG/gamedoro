import argparse

from . import state
from .daemon import Daemon


def main() -> None:
    ap = argparse.ArgumentParser(prog="gamedoro", description=__doc__)
    ap.add_argument("--play", type=float, default=50, metavar="MIN",
                    help="minutes of play allowed per cycle (default: 50)")
    ap.add_argument("--block", type=float, default=10, metavar="MIN",
                    help="minutes games stay frozen (default: 10)")
    ap.add_argument("--first-bonus", type=float, default=10, metavar="MIN",
                    help="extra minutes added to the first play cycle, to cover "
                         "game loading (default: 10; 0 disables)")
    args = ap.parse_args()
    if args.play <= 0 or args.block <= 0:
        ap.error("--play and --block must be positive")
    if args.first_bonus < 0:
        ap.error("--first-bonus can't be negative")
    path = state.default_path()
    cycle = state.load(args.play * 60, args.block * 60, path,
                      first_bonus_seconds=args.first_bonus * 60)
    Daemon(cycle, state_path=path).run()


if __name__ == "__main__":
    main()
