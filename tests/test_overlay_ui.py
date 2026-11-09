import fcntl
import os
import pty
import struct
import subprocess
import sys
import tempfile
import termios
import time
import unittest
from pathlib import Path

from gamedoro import overlay_ui
from gamedoro.overlay_ui import big, clock, frame


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


class BigTest(unittest.TestCase):
    def test_every_row_has_equal_width(self):
        rows = big("12:34")
        self.assertEqual(len(rows), 5)
        self.assertEqual(len({len(r) for r in rows}), 1)


class FrameTest(unittest.TestCase):
    def test_countdown_has_no_enter_prompt(self):
        f = frame(90, 120, 40)
        self.assertIn("Time for a break", f)
        self.assertNotIn("Enter", f)

    def test_finished_prompts_for_enter(self):
        f = frame(0, 120, 40)
        self.assertIn("Press Enter to resume your game.", f)

    def test_survives_a_tiny_terminal(self):
        frame(30, 5, 3)


class InteractiveTest(unittest.TestCase):
    """Drive the real script through a pty, as a terminal emulator would."""

    def start(self, until):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.confirm = Path(d.name) / "confirmed"
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
        self.master = master
        self.proc = subprocess.Popen(
            [sys.executable, overlay_ui.__file__, "--until", str(until),
             "--confirm-file", str(self.confirm)],
            stdin=slave, stdout=slave, stderr=slave, close_fds=True)
        os.close(slave)
        self.addCleanup(lambda: (self.proc.kill(), self.proc.wait(), os.close(master)))

    def test_enter_is_ignored_until_countdown_ends(self):
        self.start(until=time.time() + 1.0)
        time.sleep(0.3)
        os.write(self.master, b"\r")  # too early
        time.sleep(0.3)
        self.assertIsNone(self.proc.poll())
        self.assertFalse(self.confirm.exists())
        time.sleep(1.0)  # countdown over
        os.write(self.master, b"x")  # wrong key
        time.sleep(0.3)
        self.assertIsNone(self.proc.poll())
        os.write(self.master, b"\r")
        self.assertEqual(self.proc.wait(timeout=3), 0)
        self.assertTrue(self.confirm.exists())

    def test_sigterm_exits_cleanly_without_confirming(self):
        self.start(until=time.time() + 60)
        time.sleep(0.3)
        self.proc.terminate()
        self.assertEqual(self.proc.wait(timeout=3), 0)
        self.assertFalse(self.confirm.exists())


if __name__ == "__main__":
    unittest.main()
