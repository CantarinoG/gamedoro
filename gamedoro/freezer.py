"""Freeze and thaw processes with SIGSTOP / SIGCONT."""

import os
import signal


def _signal_all(pids, sig) -> None:
    for pid in pids:
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            pass  # exited in the meantime
        except PermissionError:
            pass  # not ours


def freeze(pids) -> None:
    _signal_all(pids, signal.SIGSTOP)


def thaw(pids) -> None:
    _signal_all(pids, signal.SIGCONT)
