import subprocess
import time
import unittest

from gamedoro.freezer import freeze, thaw


def state(pid: int) -> str:
    with open(f"/proc/{pid}/stat") as f:
        return f.read().rsplit(")", 1)[1].split()[0]


class FreezerTest(unittest.TestCase):
    def test_freeze_then_thaw(self):
        p = subprocess.Popen(["sleep", "30"])
        self.addCleanup(p.kill)
        freeze([p.pid])
        time.sleep(0.1)
        self.assertEqual(state(p.pid), "T")
        thaw([p.pid])
        time.sleep(0.1)
        self.assertNotEqual(state(p.pid), "T")

    def test_missing_pid_is_ignored(self):
        p = subprocess.Popen(["true"])
        p.wait()
        freeze([p.pid])
        thaw([p.pid])


if __name__ == "__main__":
    unittest.main()
