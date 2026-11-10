import unittest

from gamedoro.keys import press_key


class FakeX11:
    def __init__(self, display_ok=True, keycodes=None):
        self.display_ok = display_ok
        self.keycodes = keycodes if keycodes is not None else {b"Escape": 9}
        self.calls = []

    def XOpenDisplay(self, name):
        self.calls.append(("open", name))
        return 1234 if self.display_ok else None

    def XStringToKeysym(self, name):
        return {b"Escape": 0xff1b}.get(name, 0) if name in self.keycodes else 0

    def XKeysymToKeycode(self, dpy, sym):
        return {0xff1b: self.keycodes.get(b"Escape", 0)}.get(sym, 0)

    def XFlush(self, dpy):
        self.calls.append(("flush",))

    def XCloseDisplay(self, dpy):
        self.calls.append(("close",))


class FakeXtst:
    def __init__(self, x11):
        self.x11 = x11

    def XTestFakeKeyEvent(self, dpy, code, is_press, delay):
        self.x11.calls.append(("key", code, bool(is_press)))


class PressKeyTest(unittest.TestCase):
    def press(self, name="Escape", **kw):
        x11 = FakeX11(**kw)
        slept = []
        ok = press_key(name, display=":0", libs=(x11, FakeXtst(x11)), sleep=slept.append)
        return ok, x11.calls, slept

    def test_presses_then_releases_the_key(self):
        ok, calls, slept = self.press()
        self.assertTrue(ok)
        keys = [c for c in calls if c[0] == "key"]
        self.assertEqual(keys, [("key", 9, True), ("key", 9, False)])
        self.assertEqual(len(slept), 1)  # held briefly between press and release

    def test_opens_the_requested_display_and_closes_it(self):
        ok, calls, _ = self.press()
        self.assertEqual(calls[0], ("open", b":0"))
        self.assertEqual(calls[-1], ("close",))

    def test_unknown_key_sends_nothing(self):
        ok, calls, _ = self.press("NoSuchKey")
        self.assertFalse(ok)
        self.assertEqual([c for c in calls if c[0] == "key"], [])
        self.assertEqual(calls[-1], ("close",))  # still cleans up

    def test_no_display_is_not_an_error(self):
        ok, calls, _ = self.press(display_ok=False)
        self.assertFalse(ok)

    def test_missing_libraries_are_not_an_error(self):
        def broken():
            raise OSError("libXtst.so.6: cannot open shared object file")
        import gamedoro.keys as keys
        orig, keys._load = keys._load, broken
        try:
            self.assertFalse(press_key("Escape"))
        finally:
            keys._load = orig


if __name__ == "__main__":
    unittest.main()
