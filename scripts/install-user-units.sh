#!/usr/bin/env bash
# Installs the user systemd units of ops/systemd/ into ~/.config/systemd/user and reloads systemd.
# The units are written for a clone at ~/arena; they are rewritten for the actual location of this clone.
# ARENA_PUBLISH_REPO=<owner>/<repo> sets the GitHub repository that receives the public dashboard.
# Does NOT enable or start anything: the commands to run are printed at the end. No sudo.
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
dest="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
publish_repo="${ARENA_PUBLISH_REPO:-OWNER/arena}"

if [ ! -x "$repo/.venv/bin/arena" ]; then
  echo "WARNING: $repo/.venv/bin/arena is missing. Run first: (cd $repo && uv sync)" >&2
fi
if [ "$publish_repo" = "OWNER/arena" ]; then
  echo "WARNING: ARENA_PUBLISH_REPO is not set: arena-publish.service will push to OWNER/arena." >&2
fi

mkdir -p "$dest"
for src in "$repo"/ops/systemd/arena-*.service "$repo"/ops/systemd/arena-*.timer; do
  unit="$(basename "$src")"
  sed -e "s|%h/arena|$repo|g" -e "s|OWNER/arena|$publish_repo|g" "$src" > "$dest/$unit.tmp"
  chmod 0644 "$dest/$unit.tmp"
  mv "$dest/$unit.tmp" "$dest/$unit"
  echo "installed: $dest/$unit"
done
systemctl --user daemon-reload
echo "daemon-reload done. Nothing is enabled."

cat <<MSG

To enable (run it yourself):
  loginctl enable-linger "$USER"   # once: the units run without an open session
  systemctl --user enable --now arena-cycle.timer arena-watch.timer          # spot league
  systemctl --user enable --now arena-perp-collect.timer arena-perp-watcher.timer arena-perp-hunter.service
  systemctl --user enable --now arena-site.service arena-publish.timer       # dashboard and its publication

To check:
  systemctl --user list-timers 'arena-*'
  journalctl --user -u arena-cycle.service -n 50
  uv run arena status
MSG
