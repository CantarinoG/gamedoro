import unittest

from gamedoro.sway import GameView, game_view, query_game_view


def win(pid, visible=True, cls=None, app_id=None, size=(1920, 1080), focused=False):
    return {"type": "con", "pid": pid, "visible": visible, "focused": focused, "nodes": [],
            "rect": {"x": 0, "y": 0, "width": size[0], "height": size[1]},
            "app_id": app_id, "window_properties": {"class": cls} if cls else None}


def output(x, windows, width=1920):
    ws = {"type": "workspace", "nodes": windows, "floating_nodes": []}
    return {"type": "output", "rect": {"x": x, "y": 0, "width": width, "height": 1080},
            "nodes": [ws], "floating_nodes": []}


def tree(*outputs):
    return {"type": "root", "nodes": list(outputs)}


def areas(t, pids, app_ids=()):
    return game_view(t, set(pids), set(app_ids)).areas


class AreasTest(unittest.TestCase):
    def test_matches_by_pid(self):
        t = tree(output(0, [win(100), win(7)]))
        self.assertEqual(areas(t, {100}), {(0, 0, 1920, 1080)})

    def test_matches_proton_window_class(self):
        t = tree(output(0, [win(5, cls="steam_app_620")]))
        self.assertEqual(areas(t, set(), {"620"}), {(0, 0, 1920, 1080)})

    def test_only_the_output_showing_the_game(self):
        t = tree(output(0, [win(7)]), output(1920, [win(100)], width=2560))
        self.assertEqual(areas(t, {100}), {(1920, 0, 2560, 1080)})

    def test_game_on_a_hidden_workspace_does_not_count(self):
        t = tree(output(0, [win(100, visible=False)]))
        self.assertEqual(areas(t, {100}), set())

    def test_unrelated_windows_are_ignored(self):
        t = tree(output(0, [win(7, cls="firefox")]))
        self.assertEqual(areas(t, {100}, {"620"}), set())

    def test_floating_game_windows_count(self):
        out = output(0, [])
        out["nodes"][0]["floating_nodes"] = [win(100)]
        self.assertEqual(areas(tree(out), {100}), {(0, 0, 1920, 1080)})


class WindowPidsTest(unittest.TestCase):
    def pids(self, t, pids, app_ids=()):
        return game_view(t, set(pids), set(app_ids)).window_pids

    def test_returns_the_process_owning_the_game_window(self):
        t = tree(output(0, [win(4106, cls="steam_app_12210"), win(7)]))
        self.assertEqual(self.pids(t, {4106, 3226}, {"12210"}), {4106})

    def test_found_even_when_not_visible(self):
        # on another workspace: we still need to know what to freeze
        t = tree(output(0, [win(4106, visible=False)]))
        self.assertEqual(self.pids(t, {4106}), {4106})

    def test_small_helper_windows_are_ignored(self):
        t = tree(output(0, [win(4106, cls="steam_app_12210"),
                            win(3345, cls="steam_app_12210", size=(160, 50))]))
        self.assertEqual(self.pids(t, {4106, 3345}, {"12210"}), {4106})

    def test_several_big_windows_are_all_kept(self):
        t = tree(output(0, [win(1), win(2, size=(1200, 900))]))
        self.assertEqual(self.pids(t, {1, 2}), {1, 2})

    def test_never_returns_pids_outside_the_game(self):
        # class matches but the pid isn't one of ours: don't touch it
        t = tree(output(0, [win(999, cls="steam_app_620")]))
        self.assertEqual(self.pids(t, {100}, {"620"}), set())

    def test_no_windows_gives_an_empty_set(self):
        self.assertEqual(self.pids(tree(output(0, [])), {100}), set())


class FocusTest(unittest.TestCase):
    def focused(self, t, pids):
        return game_view(t, set(pids), set()).focused

    def test_focused_game_window(self):
        t = tree(output(0, [win(100, focused=True)]))
        self.assertTrue(self.focused(t, {100}))

    def test_game_not_focused_when_something_else_is(self):
        t = tree(output(0, [win(100), win(7, focused=True)]))
        self.assertFalse(self.focused(t, {100}))

    def test_another_apps_focus_does_not_count(self):
        t = tree(output(0, [win(7, focused=True)]))
        self.assertFalse(self.focused(t, {100}))

    def test_any_focused_game_window_counts(self):
        t = tree(output(0, [win(100, size=(1920, 1080)), win(101, size=(100, 100), focused=True)]))
        self.assertTrue(self.focused(t, {100, 101}))


class QueryTest(unittest.TestCase):
    def test_runs_swaymsg_with_a_session_environment(self):
        seen = {}

        def fake_run(cmd, **kw):
            seen.update(kw)
            class R:
                stdout = b'{"type": "root", "nodes": []}'
            return R

        self.assertEqual(query_game_view({1}, set(), run=fake_run), GameView())
        self.assertIn("XDG_RUNTIME_DIR", seen["env"])

    def test_returns_none_when_sway_is_unavailable(self):
        def boom(*a, **k):
            raise FileNotFoundError("swaymsg")
        self.assertIsNone(query_game_view({1}, set(), run=boom))


if __name__ == "__main__":
    unittest.main()
