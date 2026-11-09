import subprocess
import tempfile
import unittest
from pathlib import Path

from gamedoro.overlay import Overlay


class FakeProc:
    def __init__(self, cmd):
        self.cmd, self.alive, self.killed = cmd, True, False

    def poll(self):
        return None if self.alive else 0

    def terminate(self):
        self.alive = False
        self.killed = True

    def wait(self, timeout=None):
        return 0

    kill = terminate


class OverlayTest(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.spawned = []
        self.now = 1000.0

        def spawn(cmd, **kw):
            p = FakeProc(cmd)
            self.spawned.append(p)
            return p

        self.overlay = Overlay("term --fs", Path(d.name) / "run" / "confirmed",
                               spawn=spawn, clock=lambda: self.now)

    def test_launches_ui_inside_the_terminal(self):
        self.overlay.show(until=1600.0)
        cmd = self.spawned[0].cmd
        self.assertEqual(cmd[:2], ["term", "--fs"])
        self.assertIn("overlay_ui.py", cmd[3])
        self.assertEqual(cmd[cmd.index("--until") + 1], "1600.0")
        self.assertEqual(cmd[cmd.index("--confirm-file") + 1], str(self.overlay.confirm_file))

    def test_show_does_not_spawn_twice_while_running(self):
        self.overlay.show(1600)
        self.now += 5
        self.overlay.show(1600)
        self.assertEqual(len(self.spawned), 1)

    def test_closed_overlay_comes_back_but_is_throttled(self):
        self.overlay.show(1600)
        self.spawned[0].alive = False  # user closed the window
        self.now += 0.5
        self.overlay.show(1600)
        self.assertEqual(len(self.spawned), 1)  # too soon
        self.now += 2
        self.overlay.show(1600)
        self.assertEqual(len(self.spawned), 2)

    def test_missing_terminal_disables_the_overlay(self):
        def boom(*a, **k):
            raise FileNotFoundError("term")
        self.overlay._spawn = boom
        self.overlay.show(1600)
        self.assertFalse(self.overlay.available)
        self.overlay.show(1600)  # no crash, no retry

    def test_hide_terminates_the_process(self):
        self.overlay.show(1600)
        self.overlay.hide()
        self.assertTrue(self.spawned[0].killed)
        self.assertFalse(self.overlay.running)
        self.overlay.hide()  # idempotent

    def test_confirmed_is_consumed_once(self):
        self.assertFalse(self.overlay.confirmed())
        self.overlay.confirm_file.parent.mkdir(parents=True)
        self.overlay.confirm_file.touch()
        self.assertTrue(self.overlay.confirmed())
        self.assertFalse(self.overlay.confirmed())


if __name__ == "__main__":
    unittest.main()
