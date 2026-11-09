import io
import unittest
from contextlib import redirect_stderr

from gamedoro.__main__ import build_overlay
from gamedoro.overlay import Overlay


class BuildOverlayTest(unittest.TestCase):
    def test_disabled_gives_no_overlay(self):
        self.assertIsNone(build_overlay(False, check=lambda: (True, "")))

    def test_available_bindings_give_an_overlay(self):
        self.assertIsInstance(build_overlay(True, check=lambda: (True, "")), Overlay)

    def test_missing_bindings_warn_and_give_none(self):
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertIsNone(build_overlay(True, check=lambda: (False, "no gi")))
        self.assertIn("no gi", err.getvalue())

    def test_never_asks_about_the_live_compositor(self):
        # Regression: at login the display doesn't exist yet. The startup check
        # must only look at bindings, never at layer-shell support.
        import gamedoro.__main__ as m
        import gamedoro.overlay_ui as ui
        self.assertIs(m.bindings_available, ui.bindings_available)
        self.assertFalse(hasattr(m, "supported"))


if __name__ == "__main__":
    unittest.main()
