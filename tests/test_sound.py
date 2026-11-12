import tempfile
import unittest
from pathlib import Path

from gamedoro import sound


class FakeProc:
    def poll(self):
        return 0


class SoundTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        (self.dir / "alarm-clock-elapsed.oga").touch()
        self.spawned = []

    def spawn(self, cmd, **kw):
        self.spawned.append(cmd)
        return FakeProc()

    def play(self, setting, have=("pw-play", "paplay")):
        return sound.play(setting, which=lambda n: n if n in have else None,
                          spawn=self.spawn, sound_dir=self.dir)

    def test_empty_setting_is_silent(self):
        self.assertFalse(self.play(""))
        self.assertEqual(self.spawned, [])

    def test_default_plays_the_stock_sound_with_the_first_player(self):
        self.assertTrue(self.play("default"))
        self.assertEqual(self.spawned, [["pw-play", str(self.dir / "alarm-clock-elapsed.oga")]])

    def test_falls_back_to_another_player(self):
        self.assertTrue(self.play("default", have=("ffplay",)))
        self.assertEqual(self.spawned[0][0], "ffplay")

    def test_custom_file(self):
        mine = self.dir / "mine.wav"
        mine.touch()
        self.assertTrue(self.play(str(mine)))
        self.assertEqual(self.spawned[0][-1], str(mine))

    def test_missing_file_or_player_does_nothing(self):
        self.assertFalse(self.play(str(self.dir / "nope.wav")))
        self.assertFalse(self.play("default", have=()))
        self.assertEqual(self.spawned, [])

    def test_a_player_that_fails_to_start_is_skipped(self):
        def spawn(cmd, **kw):
            if cmd[0] == "pw-play":
                raise OSError
            return FakeProc()
        self.assertTrue(sound.play("default", which=lambda n: n, spawn=spawn,
                                   sound_dir=self.dir))


if __name__ == "__main__":
    unittest.main()
