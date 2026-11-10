import os
import tempfile
import unittest
from pathlib import Path

from gamedoro.config import ConfigError, Settings, Watcher, resolve


class ConfigTest(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.path = Path(d.name) / "gamedoro" / "config.toml"
        self.writes = 0

    def write(self, text):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(text)
        # File timestamps are coarse, so give every write its own mtime.
        self.writes += 1
        os.utime(self.path, (1_000_000 + self.writes, 1_000_000 + self.writes))

    def test_missing_file_gives_defaults(self):
        self.assertEqual(resolve(self.path), Settings())

    def test_file_overrides_defaults(self):
        self.write("play = 30\nblock = 5.5\noverlay = false\n")
        s = resolve(self.path)
        self.assertEqual((s.play, s.block, s.launch_bonus, s.overlay), (30, 5.5, 10, False))

    def test_flags_override_the_file(self):
        self.write("play = 30\nblock = 5\n")
        s = resolve(self.path, {"play": 45, "block": None, "overlay": None})
        self.assertEqual((s.play, s.block), (45, 5))  # None = flag not given

    def test_old_first_bonus_name_still_works(self):
        self.write("first_bonus = 4\n")
        self.assertEqual(resolve(self.path).launch_bonus, 4)

    def test_setting_both_names_is_an_error(self):
        self.write("first_bonus = 4\nlaunch_bonus = 5\n")
        with self.assertRaisesRegex(ConfigError, "not both"):
            resolve(self.path)

    def test_pulse_defaults_and_overrides(self):
        s = resolve(self.path)
        self.assertEqual((s.pulse_every_seconds, s.pulse_for_seconds), (30, 1))
        self.write("pulse_every_seconds = 45\npulse_for_seconds = 2\n")
        s = resolve(self.path)
        self.assertEqual((s.pulse_every_seconds, s.pulse_for_seconds), (45, 2))

    def test_pulse_can_be_disabled(self):
        self.write("pulse_every_seconds = 0\n")
        self.assertEqual(resolve(self.path).pulse_every_seconds, 0)

    def test_pulse_values_are_validated(self):
        for text in ("pulse_every_seconds = -1\n",
                     "pulse_for_seconds = 0\n",
                     "pulse_every_seconds = 10\npulse_for_seconds = 10\n",
                     "pulse_every_seconds = 10\npulse_for_seconds = 30\n"):
            self.write(text)
            with self.assertRaises(ConfigError, msg=text):
                resolve(self.path)

    def test_pause_key_defaults_to_escape_and_can_change_or_be_disabled(self):
        self.assertEqual(resolve(self.path).pause_key, "Escape")
        self.write('pause_key = "p"\npause_wait_seconds = 3\n')
        s = resolve(self.path)
        self.assertEqual((s.pause_key, s.pause_wait_seconds), ("p", 3))
        self.write('pause_key = ""\n')
        self.assertEqual(resolve(self.path).pause_key, "")

    def test_pause_key_must_be_a_string(self):
        self.write("pause_key = 27\n")
        with self.assertRaisesRegex(ConfigError, "string"):
            resolve(self.path)

    def test_negative_pause_wait_is_rejected(self):
        self.write("pause_wait_seconds = -1\n")
        with self.assertRaises(ConfigError):
            resolve(self.path)

    def test_freeze_defaults_on_and_can_be_turned_off(self):
        self.assertTrue(resolve(self.path).freeze)
        self.write("freeze = false\n")
        self.assertFalse(resolve(self.path).freeze)

    def test_freeze_must_be_true_or_false(self):
        self.write('freeze = "no"\n')
        with self.assertRaises(ConfigError):
            resolve(self.path)

    def test_unknown_key_is_rejected_by_name(self):
        self.write("plya = 30\n")
        with self.assertRaisesRegex(ConfigError, "plya"):
            resolve(self.path)

    def test_wrong_types_are_rejected(self):
        for text in ('play = "fifty"\n', "play = true\n", "overlay = 1\n"):
            self.write(text)
            with self.assertRaises(ConfigError, msg=text):
                resolve(self.path)

    def test_broken_toml_is_rejected(self):
        self.write("play = \n")
        with self.assertRaises(ConfigError):
            resolve(self.path)

    def test_values_are_validated(self):
        for text in ("play = 0\n", "block = -1\n", "launch_bonus = -5\n"):
            self.write(text)
            with self.assertRaises(ConfigError, msg=text):
                resolve(self.path)

    def test_watcher_reports_edits_once(self):
        self.write("play = 30\n")
        w = Watcher(self.path)
        self.assertEqual(w.poll(), (None, None))
        self.write("play = 20\n")
        settings, err = w.poll()
        self.assertEqual((settings.play, err), (20, None))
        self.assertEqual(w.poll(), (None, None))

    def test_watcher_reports_a_bad_edit_once_and_recovers(self):
        self.write("play = 30\n")
        w = Watcher(self.path)
        self.write("play = oops\n")
        settings, err = w.poll()
        self.assertIsNone(settings)
        self.assertIn("config.toml", err)
        self.assertEqual(w.poll(), (None, None))
        self.write("play = 25\n")
        self.assertEqual(w.poll()[0].play, 25)

    def test_watcher_keeps_cli_overrides(self):
        self.write("play = 30\n")
        w = Watcher(self.path, {"play": 45})
        self.write("play = 20\nblock = 3\n")
        s, _ = w.poll()
        self.assertEqual((s.play, s.block), (45, 3))


if __name__ == "__main__":
    unittest.main()
