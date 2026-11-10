"""Send a key press to the focused X11 (Xwayland) window, via the XTEST extension.

Used to pause a game with its own pause key just before it is frozen. Proton
games run under Xwayland, where XTEST key events go to whichever window has
keyboard focus, so callers must check that the game is focused first.

Uses ctypes on libX11/libXtst, so nothing needs installing beyond what an
Xwayland setup already has.
"""

import ctypes
import ctypes.util
import time


def _load():
    x11 = ctypes.CDLL(ctypes.util.find_library("X11") or "libX11.so.6")
    xtst = ctypes.CDLL(ctypes.util.find_library("Xtst") or "libXtst.so.6")
    x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x11.XOpenDisplay.restype = ctypes.c_void_p
    x11.XStringToKeysym.argtypes = [ctypes.c_char_p]
    x11.XStringToKeysym.restype = ctypes.c_ulong
    x11.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    x11.XKeysymToKeycode.restype = ctypes.c_ubyte
    x11.XFlush.argtypes = [ctypes.c_void_p]
    x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
    xtst.XTestFakeKeyEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                       ctypes.c_int, ctypes.c_ulong]
    return x11, xtst


def press_key(keysym: str, display: str | None = None, libs=None,
              hold: float = 0.1, sleep=time.sleep) -> bool:
    """Press and release the key named `keysym` (an X keysym name such as
    "Escape" or "p"). Returns whether it was sent; never raises."""
    try:
        x11, xtst = libs or _load()
        dpy = x11.XOpenDisplay(display.encode() if display else None)
        if not dpy:
            return False
        try:
            sym = x11.XStringToKeysym(keysym.encode())
            code = x11.XKeysymToKeycode(dpy, sym) if sym else 0
            if not code:
                return False
            xtst.XTestFakeKeyEvent(dpy, code, 1, 0)
            x11.XFlush(dpy)
            sleep(hold)
            xtst.XTestFakeKeyEvent(dpy, code, 0, 0)
            x11.XFlush(dpy)
            return True
        finally:
            x11.XCloseDisplay(dpy)
    except (OSError, AttributeError, ctypes.ArgumentError):
        return False
