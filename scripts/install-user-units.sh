#!/usr/bin/env bash
# Copie les unités systemd utilisateur de ops/systemd/ dans ~/.config/systemd/user et recharge systemd.
# N'ACTIVE ni ne démarre rien : les commandes à lancer sont affichées à la fin. Pas de sudo.
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
dest="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

if [ ! -x "$repo/.venv/bin/arene" ]; then
  echo "ATTENTION : $repo/.venv/bin/arene absent. Lance d'abord : (cd $repo && uv sync)" >&2
fi

mkdir -p "$dest"
for unit in arene-cycle.service arene-cycle.timer arene-site.service; do
  install -m 0644 "$repo/ops/systemd/$unit" "$dest/$unit"
  echo "copié : $dest/$unit"
done
systemctl --user daemon-reload
echo "daemon-reload fait. Rien n'est activé."

cat <<MSG

Pour activer (à lancer toi-même) :
  loginctl enable-linger "$USER"                      # une fois : les unités tournent sans session ouverte
  systemctl --user enable --now arene-cycle.timer     # cycle à HH:05 UTC toutes les 4 h
  systemctl --user enable --now arene-site.service    # dashboard sur http://127.0.0.1:8787

Pour vérifier :
  systemctl --user list-timers arene-cycle.timer
  journalctl --user -u arene-cycle.service -n 50
  uv run arene status
MSG
