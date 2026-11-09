"""Fullscreen countdown shown in a terminal while games are frozen.

Standalone on purpose (stdlib only, no package imports): the daemon runs it
inside a terminal emulator as `python3 overlay_ui.py --until EPOCH --confirm-file F`.

Shows the time left until EPOCH. Once it reaches zero, waits for Enter, then
creates the confirm file and exits 0. Enter is ignored during the countdown.
"""

import argparse
import os
import select
import signal
import sys
import termios
import time
import tty

DIGITS = {
    "0": ("███", "█ █", "█ █", "█ █", "███"),
    "1": (" █ ", "██ ", " █ ", " █ ", "███"),
    "2": ("███", "  █", "███", "█  ", "███"),
    "3": ("███", "  █", "███", "  █", "███"),
    "4": ("█ █", "█ █", "███", "  █", "  █"),
    "5": ("███", "█  ", "███", "  █", "███"),
    "6": ("███", "█  ", "███", "█ █", "███"),
    "7": ("███", "  █", "  █", "  █", "  █"),
    "8": ("███", "█ █", "███", "█ █", "███"),
    "9": ("███", "█ █", "███", "  █", "███"),
    ":": ("   ", " █ ", "   ", " █ ", "   "),
}

DIM, BOLD, GREEN, RESET = "\x1b[2m", "\x1b[1m", "\x1b[32m", "\x1b[0m"


def clock(seconds: float) -> str:
    """mm:ss, rounding up so the display hits 00:00 exactly when time is up."""
    total = max(0, int(-(-seconds // 1)))
    return f"{total // 60:02d}:{total % 60:02d}"


def big(text: str) -> list[str]:
    """Render text in the block font, doubling columns to look square."""
    rows = []
    for r in range(5):
        row = " ".join(DIGITS[ch][r] for ch in text)
        rows.append("".join(c * 2 for c in row))
    return rows


def frame(remaining: float, cols: int, rows: int) -> str:
    """Build the whole screen as one string, centered in cols x rows."""
    done = remaining <= 0
    lines = ["Time for a break" if not done else "Break's over",
             "",
             *big(clock(remaining)),
             "",
             "Go do something productive." if not done
             else "Press Enter to resume your game."]
    top = max(0, (rows - len(lines)) // 2)
    out = ["\x1b[H\x1b[2J" + "\n" * top]
    for i, line in enumerate(lines):
        pad = " " * max(0, (cols - len(line)) // 2)
        style = BOLD + GREEN if done and i in (0, len(lines) - 1) else (
            DIM if line == "Go do something productive." else "")
        out.append(f"{pad}{style}{line}{RESET if style else ''}")
    return "\n".join(out)


def run(until: float, confirm_file: str) -> int:
    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    try:
        tty.setcbreak(fd)
        sys.stdout.write("\x1b[?25l")  # hide cursor
        while True:
            remaining = until - time.time()
            size = os.get_terminal_size()
            sys.stdout.write(frame(remaining, size.columns, size.lines))
            sys.stdout.flush()
            ready, _, _ = select.select([fd], [], [], 0.25)
            if ready:
                key = os.read(fd, 32)
                if remaining <= 0 and (b"\n" in key or b"\r" in key):
                    with open(confirm_file, "w"):
                        pass
                    return 0
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)
        sys.stdout.write("\x1b[?25h\x1b[2J\x1b[H")
        sys.stdout.flush()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--until", type=float, required=True, help="epoch seconds")
    ap.add_argument("--confirm-file", required=True)
    args = ap.parse_args()
    sys.exit(run(args.until, args.confirm_file))


if __name__ == "__main__":
    main()
