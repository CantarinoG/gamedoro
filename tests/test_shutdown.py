import os
import signal
import subprocess
import sys
import textwrap
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# A daemon whose "game" is a sleeping child process; play time is 1s, so it
# freezes the child almost immediately.
SCRIPT = textwrap.dedent("""
    import subprocess, sys
    sys.path.insert(0, {root!r})
    from gamedoro.cycle import Cycle
    from gamedoro.daemon import Daemon
    game = subprocess.Popen(["sleep", "60"])
    print(game.pid, flush=True)
    Daemon(Cycle(1, 60), find=lambda: {{"1": [game.pid]}}, notify=lambda *a: None).run()
""")


def state(pid: int) -> str:
    with open(f"/proc/{pid}/stat") as f:
        return f.read().rsplit(")", 1)[1].split()[0]


class ShutdownTest(unittest.TestCase):
    def check_thaws_on(self, sig):
        daemon = subprocess.Popen([sys.executable, "-c", SCRIPT.format(root=str(ROOT))],
                                  stdout=subprocess.PIPE, text=True)
        game = int(daemon.stdout.readline())
        self.addCleanup(lambda: (os.kill(game, signal.SIGKILL), daemon.kill(),
                                 daemon.wait(), daemon.stdout.close()))
        for _ in range(50):  # wait for the freeze
            time.sleep(0.1)
            if state(game) == "T":
                break
        self.assertEqual(state(game), "T", "game was never frozen")
        daemon.send_signal(sig)
        self.assertEqual(daemon.wait(timeout=5), 0)
        time.sleep(0.2)
        self.assertNotEqual(state(game), "T", f"game left frozen after {sig.name}")

    def test_sighup_thaws_the_game(self):
        self.check_thaws_on(signal.SIGHUP)  # closing the terminal

    def test_sigterm_thaws_the_game(self):
        self.check_thaws_on(signal.SIGTERM)

    def test_sigint_thaws_the_game(self):
        self.check_thaws_on(signal.SIGINT)


if __name__ == "__main__":
    unittest.main()
