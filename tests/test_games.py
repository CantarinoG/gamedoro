import unittest

from gamedoro.games import find_game_pids, parse_app_id
import tempfile
from pathlib import Path


class ParseTest(unittest.TestCase):
    def test_extracts_app_id(self):
        self.assertEqual(parse_app_id(b"HOME=/x\0SteamAppId=620\0A=b\0"), "620")

    def test_missing_or_zero_is_not_a_game(self):
        self.assertIsNone(parse_app_id(b"HOME=/x\0"))
        self.assertIsNone(parse_app_id(b"SteamAppId=0\0"))
        self.assertIsNone(parse_app_id(b""))


class FindTest(unittest.TestCase):
    def make_proc(self, root, pid, environ, comm):
        d = Path(root) / str(pid)
        d.mkdir()
        (d / "environ").write_bytes(environ)
        (d / "comm").write_text(comm + "\n")

    def test_groups_pids_and_skips_steam_itself(self):
        with tempfile.TemporaryDirectory() as root:
            self.make_proc(root, 4001, b"SteamAppId=620\0", "portal2")
            self.make_proc(root, 4002, b"SteamAppId=620\0", "wineserver")
            self.make_proc(root, 4003, b"SteamAppId=620\0", "steam")
            self.make_proc(root, 4004, b"HOME=/x\0", "bash")
            (Path(root) / "self").mkdir()  # non-numeric entries are ignored
            self.assertEqual(find_game_pids(Path(root)), {"620": [4001, 4002]})


if __name__ == "__main__":
    unittest.main()
