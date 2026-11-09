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
            p.kwargs = kw
            self.spawned.append(p)
            return p

        self.overlay = Overlay(Path(d.name) / "run" / "confirmed",
                               spawn=spawn, clock=lambda: self.now)

    def test_launches_the_ui_script(self):
        self.overlay.show(until=1600.0)
        cmd = self.spawned[0].cmd
        self.assertTrue(cmd[1].endswith("overlay_ui.py"))
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

    def test_unlaunchable_overlay_is_disabled(self):
        def boom(*a, **k):
            raise FileNotFoundError("python")
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

    def test_overlay_that_keeps_dying_instantly_is_given_up_on(self):
        for _ in range(3):
            self.overlay.show(1600)
            self.spawned[-1].alive = False  # died right away
            self.now += 2.5  # past the retry throttle, still a quick death
        self.overlay.show(1600)
        self.assertFalse(self.overlay.available)
        self.assertEqual(len(self.spawned), 3)

    def test_overlay_that_lived_a_while_resets_the_count(self):
        for _ in range(2):
            self.overlay.show(1600)
            self.spawned[-1].alive = False
            self.now += 2.5
        self.overlay.show(1600)
        self.now += 60  # this one stayed up a long time
        self.spawned[-1].alive = False
        self.overlay.show(1600)
        self.assertTrue(self.overlay.available)

    def test_covers_only_the_requested_areas(self):
        self.overlay.show(1600, areas={(1920, 0, 2560, 1440), (0, 0, 1920, 1080)})
        cmd = self.spawned[0].cmd
        areas = [cmd[i + 1] for i, a in enumerate(cmd) if a == "--area"]
        self.assertEqual(areas, ["0,0,1920,1080", "1920,0,2560,1440"])

    def test_no_areas_means_every_screen(self):
        self.overlay.show(1600)
        self.assertNotIn("--area", self.spawned[0].cmd)

    def test_moves_to_the_new_screen_immediately_when_areas_change(self):
        self.overlay.show(1600, areas={(0, 0, 1920, 1080)})
        self.now += 0.1  # well inside the respawn throttle
        self.overlay.show(1600, areas={(1920, 0, 1920, 1080)})
        self.assertEqual(len(self.spawned), 2)
        self.assertTrue(self.spawned[0].killed)
        self.assertIn("1920,0,1920,1080", self.spawned[1].cmd)

    def test_same_areas_do_not_restart(self):
        self.overlay.show(1600, areas={(0, 0, 1920, 1080)})
        self.overlay.show(1600, areas={(0, 0, 1920, 1080)})
        self.assertEqual(len(self.spawned), 1)

    def test_deliberate_restarts_do_not_count_as_failures(self):
        for i in range(5):
            self.overlay.show(1600, areas={(i, 0, 100, 100)})
        self.assertTrue(self.overlay.available)

    def test_spawns_with_a_session_environment(self):
        self.overlay.show(1600)
        env = self.spawned[0].kwargs["env"]
        self.assertIn("XDG_RUNTIME_DIR", env)  # filled in even when launched by systemd


if __name__ == "__main__":
    unittest.main()
