# gamedoro

A gamified pomodoro for Steam on Linux. You may play for X minutes; then every
running Steam game is frozen (`SIGSTOP`) for Y minutes. The game stays open,
it just stops until the block ends, then resumes where it left off.

Python 3.11+, stdlib only for the core. The overlay additionally needs GTK 3 and
gtk-layer-shell bindings (Debian/Ubuntu: `sudo apt install gir1.2-gtk-3.0
gir1.2-gtklayershell-0.1`) and a compositor with wlr-layer-shell, like sway.
Without them gamedoro warns and runs with no overlay. `notify-send` is used for
notifications if present.

## Usage

    python3 -m gamedoro                      # uses ~/.config/gamedoro/config.toml
    python3 -m gamedoro --play 30 --block 5  # flags override the file

### Settings

`~/.config/gamedoro/config.toml` (see `config.example.toml`):

    play = 50         # minutes of play per cycle
    block = 10        # minutes games stay frozen
    launch_bonus = 10 # extra minutes each time a game launches (loading screens)
    overlay = true    # countdown screen + wait for Enter; false = blocks just end

Precedence: built-in defaults < config file < command-line flags
(`--play`, `--block`, `--launch-bonus`, `--no-overlay`, `--config FILE`).
`first_bonus` / `--first-bonus` are the old names and still work.

While the daemon runs, edits to the file are picked up within a few seconds
and you get a notification. They apply **from the next cycle**: a play budget or
block already in progress keeps the length it started with, so you can't
shorten a block by editing the file. A broken edit is reported and the old
settings stay. (`overlay` and flags need a restart. `launch_bonus` applies immediately.)

### Run on login

    ./install.sh          # install + enable; starts at your next login
    ./install.sh --now    # ...and start it right away
    ./install.sh uninstall

This writes a systemd **user** service with absolute paths, so it doesn't matter
where the repo lives. The service finds sway's Wayland sockets itself, so no
sway config changes are needed. Useful commands:

    systemctl --user status gamedoro
    systemctl --user restart gamedoro      # e.g. after changing flags
    journalctl --user -u gamedoro -f       # logs

A config error at startup makes the service stop (and show as failed) instead of
restart-looping; fix the file and `systemctl --user start gamedoro`.

### Behaviour

- The play budget only drains **while a Steam game is running**.
- **Launch bonus:** every time a game launches (none was running before), your
  budget is topped up by `launch_bonus` minutes, since loading isn't play time.
  It's capped at `play + launch_bonus`, so relaunching can't stack bonuses. A game
  already running when the daemon starts, or launched during a block, gets none.
- A warning notification appears with 1 minute of play left.
- When the budget is spent, all game processes are frozen for the block.
  Games launched during a block are frozen too.
- A fullscreen overlay shows the countdown. When it hits zero the game stays
  frozen until you press **Enter** on the overlay.
- The overlay only covers the screen where the frozen game is visible. Switch
  to another workspace and it disappears, so you can keep using your PC; switch
  back and it returns. It doesn't take the keyboard during the countdown, only
  once it's asking for Enter. If you quit the game mid-block the overlay goes
  away too (the block timer keeps running).
- Stopping the daemon (Ctrl-C, SIGTERM, or closing its terminal / SIGHUP)
  thaws everything it froze.
- State lives in `~/.local/state/gamedoro/state.json`. A block keeps counting
  down while the daemon is off, so restarting it doesn't skip the block.

## How it works

| Module | Role |
| --- | --- |
| `cycle.py` | Pure play/block state machine |
| `games.py` | Finds games by scanning `/proc/*/environ` for `SteamAppId` |
| `freezer.py` | `SIGSTOP` / `SIGCONT` |
| `config.py` | Config file, defaults/flags precedence, live reload watcher |
| `env.py` | Finds the Wayland/sway sockets when run as a service |
| `state.py` | Save/restore across restarts |
| `overlay.py` | Launches/respawns the overlay process, reads the Enter confirmation |
| `sway.py` | Asks sway which screens currently show a game window |
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
