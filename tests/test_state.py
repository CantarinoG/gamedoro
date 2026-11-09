import tempfile
import unittest
from pathlib import Path

from gamedoro.cycle import Cycle, Phase
from gamedoro.state import load, save


class StateTest(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.path = Path(d.name) / "sub" / "state.json"

    def test_missing_file_starts_fresh(self):
        c = load(60, 10, self.path)
        self.assertEqual((c.phase, c.remaining), (Phase.PLAYING, 60))

    def test_corrupt_file_starts_fresh(self):
        self.path.parent.mkdir()
        self.path.write_text("{not json")
        self.assertEqual(load(60, 10, self.path).remaining, 60)

    def test_play_budget_is_restored(self):
        save(Cycle(60, 10, remaining=25), self.path, now=1000)
        c = load(60, 10, self.path, now=5000)  # time off doesn't matter
        self.assertEqual((c.phase, c.remaining), (Phase.PLAYING, 25))

    def test_block_keeps_counting_while_daemon_is_off(self):
        save(Cycle(60, 10, Phase.BLOCKED, 10), self.path, now=1000)
        c = load(60, 10, self.path, now=1004)
        self.assertEqual((c.phase, c.remaining), (Phase.BLOCKED, 6))

    def test_expired_block_returns_to_fresh_play(self):
        save(Cycle(60, 10, Phase.BLOCKED, 10), self.path, now=1000)
        c = load(60, 10, self.path, now=1011)
        self.assertEqual((c.phase, c.remaining), (Phase.PLAYING, 60))

    def test_remaining_above_new_config_is_not_trusted(self):
        save(Cycle(120, 10, remaining=100), self.path, now=1000)
        self.assertEqual(load(60, 10, self.path).remaining, 60)

    def test_fresh_start_includes_first_bonus(self):
        self.assertEqual(load(60, 10, self.path, first_bonus_seconds=15).remaining, 75)

    def test_restored_bonus_budget_is_trusted(self):
        save(Cycle(60, 10, remaining=70), self.path, now=1000)
        self.assertEqual(load(60, 10, self.path, first_bonus_seconds=15).remaining, 70)

    def test_saved_budget_doesnt_gain_a_bonus(self):
        save(Cycle(60, 10, remaining=20), self.path, now=1000)
        self.assertEqual(load(60, 10, self.path, first_bonus_seconds=15).remaining, 20)


if __name__ == "__main__":
    unittest.main()
