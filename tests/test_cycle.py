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

    def test_block_end_waits_for_resume(self):
        c = Cycle(play_seconds=4, block_seconds=2)
        c.tick(4, True)
        self.assertEqual(c.tick(2, False), Phase.READY)
        self.assertIsNone(c.tick(5, True))  # time passing changes nothing
        self.assertEqual(c.phase, Phase.READY)

    def test_resume_starts_fresh_budget(self):
        c = Cycle(play_seconds=4, block_seconds=2)
        c.tick(4, True)
        c.tick(2, False)
        self.assertTrue(c.resume())
        self.assertEqual((c.phase, c.remaining), (Phase.PLAYING, 4))

    def test_resume_only_works_when_ready(self):
        c = Cycle(play_seconds=4, block_seconds=2)
        self.assertFalse(c.resume())
        c.tick(4, True)
        self.assertFalse(c.resume())  # still blocked
        self.assertEqual(c.phase, Phase.BLOCKED)

    def test_long_ticks_are_clamped(self):
        c = Cycle(play_seconds=100, block_seconds=5)
        c.tick(3600, True)  # e.g. laptop resumed from suspend
        self.assertEqual(c.remaining, 95)

    def test_launch_bonus_tops_up_the_budget(self):
        c = Cycle(play_seconds=60, block_seconds=5)
        c.remaining = 20
        self.assertEqual(c.launch_bonus(10), 10)
        self.assertEqual(c.remaining, 30)

    def test_launch_bonus_is_capped_at_play_plus_bonus(self):
        c = Cycle(play_seconds=60, block_seconds=5)
        self.assertEqual(c.launch_bonus(10), 10)  # fresh budget: 60 -> 70
        self.assertEqual(c.remaining, 70)
        self.assertEqual(c.launch_bonus(10), 0)   # relaunching can't stack
        c.remaining = 65
        self.assertEqual(c.launch_bonus(10), 5)   # only up to the cap
        self.assertEqual(c.remaining, 70)

    def test_launch_bonus_only_applies_while_playing(self):
        c = Cycle(play_seconds=4, block_seconds=2)
        c.tick(4, True)  # BLOCKED
        self.assertEqual(c.launch_bonus(10), 0)
        self.assertEqual(c.remaining, 2)
        c.tick(2, False)  # READY
        self.assertEqual(c.launch_bonus(10), 0)

    def test_bonus_is_not_spent_while_no_game_runs(self):
        c = Cycle(play_seconds=4, block_seconds=2)
        c.launch_bonus(3)
        c.tick(5, False)
        self.assertEqual(c.remaining, 7)


if __name__ == "__main__":
    unittest.main()
