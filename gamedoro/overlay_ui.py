"""Fullscreen countdown shown over everything while games are frozen.

Standalone on purpose: the daemon runs it as a subprocess,
`python3 overlay_ui.py --until EPOCH --confirm-file F [--area X,Y,W,H ...]`, so a
crash here can't take the daemon down. With --area it covers only the screens
with that geometry (all screens if none are given or none match).

It is a wlr-layer-shell surface on the OVERLAY layer, which sway draws above
fullscreen windows without touching them (unlike a normal window, which would
make sway un-fullscreen the game). The keyboard is left alone during the
countdown and grabbed only once Enter is being asked for, because an exclusive
grab would otherwise stop you typing in anything else.

Shows the time left until EPOCH. At zero it asks for Enter, then creates the
confirm file and exits 0. Enter is ignored during the countdown.
"""

import argparse
import sys
import time

CSS = b"""
window { background-color: rgba(10, 10, 20, 0.96); }
.title { color: #cdd6f4; font-size: 36px; }
.clock { color: #f5e0dc; font-size: 160px; font-weight: bold; }
.hint  { color: #a6adc8; font-size: 28px; }
.ready { color: #a6e3a1; }
"""


def clock(seconds: float) -> str:
    """mm:ss, rounding up so the display hits 00:00 exactly when time is up."""
    total = max(0, int(-(-seconds // 1)))
    return f"{total // 60:02d}:{total % 60:02d}"


def texts(remaining: float) -> tuple[str, str, str]:
    """(title, clock, hint) for the given time left."""
    if remaining > 0:
        return "Time for a break", clock(remaining), ""
    return "Break's over", clock(0), "Press Enter to resume your game."


def supported() -> tuple[bool, str]:
    """Can this Python show the overlay? Returns (ok, reason if not)."""
    try:
        import gi
        gi.require_version("Gtk", "3.0")
        gi.require_version("GtkLayerShell", "0.1")
        from gi.repository import GtkLayerShell
    except (ImportError, ValueError) as e:
        return False, (f"{e}. On Debian/Ubuntu: "
                       "sudo apt install gir1.2-gtk-3.0 gir1.2-gtklayershell-0.1")
    if not GtkLayerShell.is_supported():
        return False, "compositor doesn't support wlr-layer-shell"
    return True, ""


def parse_area(text: str) -> tuple[int, int, int, int]:
    x, y, w, h = (int(v) for v in text.split(","))
    return x, y, w, h


def pick_monitors(geometries: list, areas: list) -> list[int]:
    """Indexes of the monitors to cover. Falls back to all if nothing matches
    (better a too-big overlay than none: the game is already frozen)."""
    if not areas:
        return list(range(len(geometries)))
    picked = [i for i, g in enumerate(geometries) if g in areas]
    return picked or list(range(len(geometries)))


def run(until: float, confirm_file: str, areas: list) -> int:
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import Gdk, GLib, Gtk, GtkLayerShell

    provider = Gtk.CssProvider()
    provider.load_from_data(CSS)
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    labels = []  # (title, clock, hint) label triples, one per monitor
    windows = []

    def build(monitor):
        win = Gtk.Window()
        GtkLayerShell.init_for_window(win)
        GtkLayerShell.set_namespace(win, "gamedoro")
        GtkLayerShell.set_layer(win, GtkLayerShell.Layer.OVERLAY)
        GtkLayerShell.set_monitor(win, monitor)
        for edge in (GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.BOTTOM,
                     GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT):
            GtkLayerShell.set_anchor(win, edge, True)
        GtkLayerShell.set_exclusive_zone(win, -1)  # cover bars too
        GtkLayerShell.set_keyboard_mode(win, GtkLayerShell.KeyboardMode.NONE)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24,
                      halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        trio = []
        for css in ("title", "clock", "hint"):
            lbl = Gtk.Label()
            lbl.get_style_context().add_class(css)
            box.pack_start(lbl, False, False, 0)
            trio.append(lbl)
        win.add(box)
        win.connect("key-press-event", on_key)
        win.show_all()
        windows.append(win)
        labels.append(trio)  # tick() shows/hides the hint as needed

    def on_key(_win, event):
        if until - time.time() <= 0 and event.keyval in (
                Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_ISO_Enter):
            with open(confirm_file, "w"):
                pass
            Gtk.main_quit()
        return True  # swallow every key; nothing else should reach the game

    def tick():
        title, clk, hint = texts(until - time.time())
        done = until - time.time() <= 0
        if done and not grabbed:
            # Now (and only now) we need Enter, so take the keyboard.
            grabbed.append(True)
            GtkLayerShell.set_keyboard_mode(
                windows[0], GtkLayerShell.KeyboardMode.EXCLUSIVE)
        for t, c, h in labels:
            t.set_text(title)
            c.set_text(clk)
            h.set_text(hint)
            h.set_visible(bool(hint))
            for lbl in (t, h):
                ctx = lbl.get_style_context()
                (ctx.add_class if done else ctx.remove_class)("ready")
        return True

    grabbed = []
    display = Gdk.Display.get_default()
    monitors = [display.get_monitor(i) for i in range(display.get_n_monitors())]
    geometries = [(m.get_geometry().x, m.get_geometry().y,
                   m.get_geometry().width, m.get_geometry().height) for m in monitors]
    for i in pick_monitors(geometries, areas):
        build(monitors[i])
    tick()
    GLib.timeout_add(250, tick)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, 15, Gtk.main_quit)  # SIGTERM
    Gtk.main()
    return 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--until", type=float, required=True, help="epoch seconds")
    ap.add_argument("--confirm-file", required=True)
    ap.add_argument("--area", action="append", default=[], type=parse_area,
                    metavar="X,Y,W,H", help="cover only this screen (repeatable)")
    args = ap.parse_args()
    ok, reason = supported()
    if not ok:
        print(f"gamedoro overlay: {reason}", file=sys.stderr)
        sys.exit(2)
    sys.exit(run(args.until, args.confirm_file, args.area))


if __name__ == "__main__":
    main()
