import unittest

from gamedoro.cycle import Cycle, Phase
from gamedoro.daemon import OVERLAY_MARGIN, Daemon


class FakeOverlay:
    def __init__(self):
        self.available = True
        self.shown = []  # `until` of every show() call
        self.hidden = 0
        self.enter_pressed = False

    def show(self, until):
        self.shown.append(until)

    def hide(self):
        self.hidden += 1

    def confirmed(self):
        pressed, self.enter_pressed = self.enter_pressed, False
        return pressed


class Harness:
    def __init__(self, play=10, block=5, overlay=None):
        self.pids = {"1": [100, 101]}
        self.frozen, self.thawed, self.notes = [], [], []
        self.daemon = Daemon(
            Cycle(play, block),
            find=lambda: self.pids,
            freeze=lambda p: self.frozen.append(set(p)),
            thaw=lambda p: self.thawed.append(set(p)),
            notify=lambda title, body="": self.notes.append(title),
            overlay=overlay,
            clock=lambda: 1000.0,
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


class OverlayTest(unittest.TestCase):
    def blocked(self, block=5):
        o = FakeOverlay()
        h = Harness(play=1, block=block, overlay=o)
        h.daemon.step(1)  # play time over -> BLOCKED
        return h, o

    def test_overlay_counts_down_to_the_end_of_the_block(self):
        h, o = self.blocked(block=5)
        self.assertEqual(o.shown, [1000.0 + 5 + OVERLAY_MARGIN])

    def test_game_stays_frozen_until_enter_is_pressed(self):
        h, o = self.blocked(block=2)
        h.daemon.step(2)  # block over -> READY
        self.assertEqual(h.daemon.cycle.phase, Phase.READY)
        self.assertEqual(h.thawed, [])
        self.assertIn("Block over", h.notes)
        for _ in range(3):
            h.daemon.step(1)
        self.assertEqual(h.daemon.cycle.phase, Phase.READY)
        self.assertEqual(h.thawed, [])

        o.enter_pressed = True
        h.daemon.step(1)
        self.assertEqual(h.daemon.cycle.phase, Phase.PLAYING)
        self.assertEqual(h.thawed, [{100, 101}])
        self.assertGreaterEqual(o.hidden, 1)
        self.assertEqual(h.notes.count("Block over"), 2)  # prompt, then resumed

    def test_enter_during_the_countdown_is_discarded(self):
        h, o = self.blocked(block=3)
        o.enter_pressed = True
        h.daemon.step(1)  # still BLOCKED
        h.daemon.step(2)  # -> READY
        self.assertEqual(h.daemon.cycle.phase, Phase.READY)  # old Enter didn't count

    def test_quitting_the_game_mid_block_hides_the_overlay(self):
        h, o = self.blocked()
        h.pids = {}
        h.daemon.step(1)
        self.assertEqual(o.hidden, 1)
        self.assertEqual(h.daemon.cycle.phase, Phase.BLOCKED)  # timer still runs

    def test_ready_with_no_game_resumes_without_asking(self):
        h, o = self.blocked(block=2)
        h.pids = {}
        h.daemon.step(2)
        self.assertEqual(h.daemon.cycle.phase, Phase.PLAYING)

    def test_unusable_overlay_falls_back_to_auto_resume(self):
        h, o = self.blocked(block=2)
        o.available = False
        h.daemon.step(2)
        self.assertEqual(h.daemon.cycle.phase, Phase.PLAYING)
        self.assertEqual(h.thawed, [{100, 101}])

    def test_overlay_dying_in_ready_falls_back_to_auto_resume(self):
        h, o = self.blocked(block=2)
        h.daemon.step(2)
        o.available = False  # e.g. the terminal failed to launch
        h.daemon.step(1)
        self.assertEqual(h.daemon.cycle.phase, Phase.PLAYING)

    def test_release_hides_the_overlay(self):
        h, o = self.blocked()
        h.daemon.release()
        self.assertEqual(o.hidden, 1)


if __name__ == "__main__":
    unittest.main()
