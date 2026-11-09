import argparse

from .cycle import Cycle
from .daemon import Daemon


def main() -> None:
    ap = argparse.ArgumentParser(prog="gamedoro", description=__doc__)
    ap.add_argument("--play", type=float, default=50, metavar="MIN",
                    help="minutes of play allowed per cycle (default: 50)")
    ap.add_argument("--block", type=float, default=10, metavar="MIN",
                    help="minutes games stay frozen (default: 10)")
    args = ap.parse_args()
    if args.play <= 0 or args.block <= 0:
        ap.error("--play and --block must be positive")
    Daemon(Cycle(args.play * 60, args.block * 60)).run()


if __name__ == "__main__":
    main()
