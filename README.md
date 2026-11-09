# gamedoro

A gamified pomodoro for Steam on Linux. You may play for X minutes; then every
running Steam game is frozen (`SIGSTOP`) for Y minutes. The game stays open,
it just stops until the block ends, then resumes where it left off.

Python 3.10+, stdlib only for the core. The overlay additionally needs GTK 3 and
gtk-layer-shell bindings (Debian/Ubuntu: `sudo apt install gir1.2-gtk-3.0
gir1.2-gtklayershell-0.1`) and a compositor with wlr-layer-shell, like sway.
Without them gamedoro warns and runs with no overlay. `notify-send` is used for
notifications if present.

## Usage

    python3 -m gamedoro --play 50 --block 10 --first-bonus 10 [--no-overlay]

- `--first-bonus` adds extra minutes to the **first** play cycle after the
  daemon starts with no saved state, since games take a while to load
  (default 10, `0` disables). Later cycles get exactly `--play`.
- The play budget only drains **while a Steam game is running**.
- A warning notification appears with 1 minute of play left.
- When the budget is spent, all game processes are frozen for the block.
  Games launched during a block are frozen too.
- A fullscreen overlay shows the countdown. When it hits zero the game stays
  frozen until you press **Enter** on the overlay. If you quit the game
  mid-block the overlay goes away (the block timer keeps running).
- `--no-overlay` skips the overlay and the Enter step: blocks just end.
- Stopping the daemon (Ctrl-C / SIGTERM) thaws everything it froze.
- State lives in `~/.local/state/gamedoro/state.json`. A block keeps counting
  down while the daemon is off, so restarting it doesn't skip the block.

### Run on login

    mkdir -p ~/.config/systemd/user
    cp systemd/gamedoro.service ~/.config/systemd/user/
    systemctl --user enable --now gamedoro

(Edit `WorkingDirectory` and the minutes in the unit first.) The overlay needs
the Wayland environment, which user services don't get by default. Add this to
your sway config so it is imported before the service starts:

    exec systemctl --user import-environment WAYLAND_DISPLAY SWAYSOCK

## How it works

| Module | Role |
| --- | --- |
| `cycle.py` | Pure play/block state machine |
| `games.py` | Finds games by scanning `/proc/*/environ` for `SteamAppId` |
| `freezer.py` | `SIGSTOP` / `SIGCONT` |
| `state.py` | Save/restore across restarts |
| `overlay.py` | Launches/respawns the overlay process, reads the Enter confirmation |
| `overlay_ui.py` | The GTK layer-shell countdown screen (runs as a subprocess) |
| `daemon.py` | Glues it together, 1s loop |

## Caveats

- The overlay is a layer-shell surface on purpose: a normal window would make
  sway un-fullscreen the game (resizing it). If the overlay can't stay up (3
  instant failures in a row) gamedoro notifies you and resumes blocks
  automatically instead of leaving the game frozen forever.
- Online games will likely disconnect during a block; anti-cheat may object.
- If the daemon is `SIGKILL`ed mid-block, games stay frozen until it restarts
  (or you run `kill -CONT` on them). Normal stops thaw correctly.
- Nothing stops you from killing the daemon. It's a commitment device.
- Steam keeps counting playtime while a game is frozen.

## Tests

    python3 -m unittest
