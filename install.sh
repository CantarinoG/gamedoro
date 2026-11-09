#!/usr/bin/env bash
# Install gamedoro as a systemd user service that starts when you log in.
#
#   ./install.sh            install + enable (starts at next login)
#   ./install.sh --now      ...and start it right away
#   ./install.sh uninstall  stop, disable and remove the service
#
# Settings live in ~/.config/gamedoro/config.toml (created if missing).
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
unit_dir="${GAMEDORO_UNIT_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user}"
config_dir="${XDG_CONFIG_HOME:-$HOME/.config}/gamedoro"
sctl="${SYSTEMCTL:-systemctl}"

if [[ "${1:-}" == "uninstall" ]]; then
    "$sctl" --user disable --now gamedoro.service 2>/dev/null || true
    rm -f "$unit_dir/gamedoro.service"
    "$sctl" --user daemon-reload
    echo "Removed the service. Your config ($config_dir) and state were kept."
    exit 0
fi

python="$(command -v python3)"
mkdir -p "$unit_dir" "$config_dir"
sed -e "s|@REPO@|$repo|" -e "s|@PYTHON@|$python|" \
    "$repo/systemd/gamedoro.service" > "$unit_dir/gamedoro.service"
echo "Installed $unit_dir/gamedoro.service"

if [[ ! -e "$config_dir/config.toml" ]]; then
    cp "$repo/config.example.toml" "$config_dir/config.toml"
    echo "Created $config_dir/config.toml"
fi

"$sctl" --user daemon-reload
if [[ "${1:-}" == "--now" ]]; then
    "$sctl" --user enable --now gamedoro.service
    echo "Enabled and started."
else
    "$sctl" --user enable gamedoro.service
    echo "Enabled. It will start at your next login (or run: systemctl --user start gamedoro)."
fi
