import unittest

from gamedoro.cycle import Cycle
from gamedoro.daemon import Daemon


class Harness:
    def __init__(self, play=10, block=5):
        self.pids = {"1": [100, 101]}
        self.frozen, self.thawed, self.notes = [], [], []
        self.daemon = Daemon(
            Cycle(play, block),
            find=lambda: self.pids,
            freeze=lambda p: self.frozen.append(set(p)),
            thaw=lambda p: self.thawed.append(set(p)),
            notify=lambda title, body="": self.notes.append(title),
        )


class DaemonTest(unittest.TestCase):
    def test_freezes_when_play_time_runs_out(self):
        h = Harness(play=4)
        h.daemon.step(2)
        self.assertEqual(h.frozen, [])
        h.daemon.step(2)
        self.assertEqual(h.frozen, [{100, 101}])
        self.assertIn("Time's up!", h.notes)

    def test_catches_game_launched_during_block(self):
        h = Harness(play=1, block=5)
        h.daemon.step(1)
        h.pids = {"1": [100, 101], "2": [200]}
        h.daemon.step(1)
        self.assertEqual(h.frozen[-1], {100, 101, 200})

    def test_thaws_everything_when_block_ends(self):
        h = Harness(play=1, block=2)
        h.daemon.step(1)
        h.pids = {}  # game frozen, then user quit it
        h.daemon.step(2)
        self.assertEqual(h.thawed, [{100, 101}])
        self.assertIn("Block over", h.notes)

    def test_release_is_idempotent(self):
        h = Harness(play=1)
        h.daemon.step(1)
        h.daemon.release()
        h.daemon.release()
        self.assertEqual(h.thawed, [{100, 101}, set()])

    def test_warns_once_before_blocking(self):
        h = Harness(play=70)
        for _ in range(2):
            h.daemon.step(5)  # 60s left: warn
        self.assertEqual(h.notes, ["1 minute of play left"])
        h.daemon.step(5)
        self.assertEqual(h.notes, ["1 minute of play left"])  # only once


if __name__ == "__main__":
    unittest.main()
