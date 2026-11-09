import unittest

from gamedoro.overlay_ui import clock, supported, texts


class ClockTest(unittest.TestCase):
    def test_formats_minutes_and_seconds(self):
        self.assertEqual(clock(0), "00:00")
        self.assertEqual(clock(65), "01:05")
        self.assertEqual(clock(600), "10:00")

    def test_rounds_up_so_zero_means_done(self):
        self.assertEqual(clock(0.2), "00:01")
        self.assertEqual(clock(-3), "00:00")

    def test_blocks_over_an_hour_keep_counting_minutes(self):
        self.assertEqual(clock(75 * 60), "75:00")


class TextsTest(unittest.TestCase):
    def test_countdown_has_no_enter_prompt(self):
        title, clk, hint = texts(90)
        self.assertEqual(clk, "01:30")
        self.assertNotIn("Enter", hint)

    def test_finished_prompts_for_enter(self):
        title, clk, hint = texts(0)
        self.assertEqual(clk, "00:00")
        self.assertIn("Enter", hint)


class SupportedTest(unittest.TestCase):
    def test_reports_a_reason_when_unsupported(self):
        ok, reason = supported()
        self.assertEqual(ok, reason == "")


if __name__ == "__main__":
    unittest.main()
