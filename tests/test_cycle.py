import unittest

from gamedoro.cycle import Cycle, Phase


class CycleTest(unittest.TestCase):
    def test_budget_only_drains_while_game_runs(self):
        c = Cycle(play_seconds=10, block_seconds=5)
        c.tick(3, game_running=False)
        self.assertEqual(c.remaining, 10)
        c.tick(3, game_running=True)
        self.assertEqual(c.remaining, 7)

    def test_blocks_when_budget_is_spent(self):
        c = Cycle(play_seconds=4, block_seconds=5)
        self.assertIsNone(c.tick(3, True))
        self.assertEqual(c.tick(2, True), Phase.BLOCKED)
        self.assertEqual(c.remaining, 5)

    def test_block_counts_down_even_without_a_game(self):
        c = Cycle(play_seconds=1, block_seconds=5)
        c.tick(2, True)
        c.tick(2, False)
        self.assertEqual(c.remaining, 3)

    def test_returns_to_playing_with_fresh_budget(self):
        c = Cycle(play_seconds=4, block_seconds=2)
        c.tick(4, True)
        self.assertEqual(c.tick(2, False), Phase.PLAYING)
        self.assertEqual(c.remaining, 4)

    def test_long_ticks_are_clamped(self):
        c = Cycle(play_seconds=100, block_seconds=5)
        c.tick(3600, True)  # e.g. laptop resumed from suspend
        self.assertEqual(c.remaining, 95)


if __name__ == "__main__":
    unittest.main()
