import unittest

from gamedoro.sway import game_areas, query_game_areas


def win(pid, visible=True, cls=None, app_id=None):
    return {"type": "con", "pid": pid, "visible": visible, "nodes": [],
            "app_id": app_id, "window_properties": {"class": cls} if cls else None}


def output(x, windows, width=1920):
    ws = {"type": "workspace", "nodes": windows, "floating_nodes": []}
    return {"type": "output", "rect": {"x": x, "y": 0, "width": width, "height": 1080},
            "nodes": [ws], "floating_nodes": []}


def tree(*outputs):
    return {"type": "root", "nodes": list(outputs)}


class GameAreasTest(unittest.TestCase):
    def test_matches_by_pid(self):
        t = tree(output(0, [win(100), win(7)]))
        self.assertEqual(game_areas(t, {100}, set()), {(0, 0, 1920, 1080)})

    def test_matches_proton_window_class(self):
        t = tree(output(0, [win(5, cls="steam_app_620")]))
        self.assertEqual(game_areas(t, set(), {"620"}), {(0, 0, 1920, 1080)})

    def test_only_the_output_showing_the_game(self):
        t = tree(output(0, [win(7)]), output(1920, [win(100)], width=2560))
        self.assertEqual(game_areas(t, {100}, set()), {(1920, 0, 2560, 1080)})

    def test_game_on_a_hidden_workspace_does_not_count(self):
        t = tree(output(0, [win(100, visible=False)]))
        self.assertEqual(game_areas(t, {100}, set()), set())

    def test_unrelated_windows_are_ignored(self):
        t = tree(output(0, [win(7, cls="firefox")]))
        self.assertEqual(game_areas(t, {100}, {"620"}), set())

    def test_floating_game_windows_count(self):
        out = output(0, [])
        out["nodes"][0]["floating_nodes"] = [win(100)]
        self.assertEqual(game_areas(tree(out), {100}, set()), {(0, 0, 1920, 1080)})


class QueryTest(unittest.TestCase):
    def test_returns_none_when_sway_is_unavailable(self):
        def boom(*a, **k):
            raise FileNotFoundError("swaymsg")
        self.assertIsNone(query_game_areas({1}, set(), run=boom))


if __name__ == "__main__":
    unittest.main()
