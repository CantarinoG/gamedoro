import os
import tempfile
import unittest
from pathlib import Path

from gamedoro.env import session_env


class SessionEnvTest(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.run_dir = Path(d.name)

    def touch(self, name, mtime=None):
        p = self.run_dir / name
        p.touch()
        if mtime:
            os.utime(p, (mtime, mtime))
        return p

    def test_finds_both_sockets_when_unset(self):
        self.touch("wayland-1")
        self.touch("wayland-1.lock")
        sock = self.touch("sway-ipc.1000.42.sock")
        env = session_env({}, self.run_dir)
        self.assertEqual(env["WAYLAND_DISPLAY"], "wayland-1")  # not the .lock
        self.assertEqual(env["SWAYSOCK"], str(sock))

    def test_live_values_are_kept(self):
        self.touch("wayland-1")
        self.touch("wayland-9")
        live = self.touch("sway-ipc.1000.7.sock")
        self.touch("sway-ipc.1000.42.sock", mtime=9_999_999_999)  # newer, but not ours
        base = {"WAYLAND_DISPLAY": "wayland-9", "SWAYSOCK": str(live)}
        env = session_env(base, self.run_dir)
        self.assertEqual(env["WAYLAND_DISPLAY"], "wayland-9")
        self.assertEqual(env["SWAYSOCK"], str(live))

    def test_stale_values_are_replaced(self):
        # e.g. imported into the user manager before sway restarted
        self.touch("wayland-2")
        fresh = self.touch("sway-ipc.1000.99.sock")
        base = {"WAYLAND_DISPLAY": "wayland-1",
                "SWAYSOCK": str(self.run_dir / "sway-ipc.1000.1.sock")}
        env = session_env(base, self.run_dir)
        self.assertEqual(env["WAYLAND_DISPLAY"], "wayland-2")
        self.assertEqual(env["SWAYSOCK"], str(fresh))

    def test_stale_value_with_nothing_to_replace_it_is_kept(self):
        env = session_env({"WAYLAND_DISPLAY": "wayland-1"}, self.run_dir)
        self.assertEqual(env["WAYLAND_DISPLAY"], "wayland-1")  # best effort

    def test_prefers_the_newest_sway_socket(self):
        self.touch("sway-ipc.1000.1.sock", mtime=1000)
        new = self.touch("sway-ipc.1000.2.sock", mtime=2000)
        self.assertEqual(session_env({}, self.run_dir)["SWAYSOCK"], str(new))

    def test_nothing_found_leaves_them_unset(self):
        env = session_env({}, self.run_dir)
        self.assertNotIn("WAYLAND_DISPLAY", env)
        self.assertNotIn("SWAYSOCK", env)

    def test_does_not_modify_the_given_environment(self):
        base = {}
        self.touch("wayland-1")
        session_env(base, self.run_dir)
        self.assertEqual(base, {})


if __name__ == "__main__":
    unittest.main()
