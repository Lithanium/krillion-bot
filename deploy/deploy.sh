#!/usr/bin/env bash
# Deploy / update the bot on a VM over ssh.
#
#   ./deploy/deploy.sh ubuntu@203.0.113.7                 # uses your default ssh key
#   ./deploy/deploy.sh ubuntu@203.0.113.7 ~/.ssh/oracle.key
#
# Copies this checkout (git-tracked files + your local .env if the VM has none)
# to ~/krillion-bot on the VM and runs deploy/setup-vm.sh there.
set -euo pipefail

if [ $# -lt 1 ]; then
    echo "usage: $0 user@host [ssh-key]" >&2
    exit 1
fi

HOST="$1"
KEY="${2:-}"
APP_DIR="${APP_DIR:-krillion-bot}"   # relative to the remote user's home

SSH=(ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new)
if [ -n "$KEY" ]; then
    SSH+=(-i "$KEY")
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

echo "==> Uploading to $HOST:~/$APP_DIR"
"${SSH[@]}" "$HOST" "mkdir -p ~/$APP_DIR"
# Ship the working tree minus anything gitignored (no venv, db or .env).
git ls-files -z --cached --others --exclude-standard \
    | while IFS= read -r -d '' f; do [ -e "$f" ] && printf '%s\0' "$f"; done \
    | tar --null -T - -czf - \
    | "${SSH[@]}" "$HOST" "tar -xzf - -C ~/$APP_DIR"

if [ -f .env ]; then
    # Only seed the remote .env once; never clobber a token that is already there.
    if ! "${SSH[@]}" "$HOST" "test -s ~/$APP_DIR/.env"; then
        echo "==> Seeding remote .env from local .env"
        "${SSH[@]}" "$HOST" "cat > ~/$APP_DIR/.env && chmod 600 ~/$APP_DIR/.env" < .env
    fi
fi

echo "==> Running setup on the VM"
"${SSH[@]}" -t "$HOST" "APP_DIR=\$HOME/$APP_DIR bash ~/$APP_DIR/deploy/setup-vm.sh"

echo
echo "Done. Useful commands:"
echo "  ${SSH[*]} $HOST 'sudo journalctl -u krillion-bot -f'      # live logs"
echo "  ${SSH[*]} $HOST 'sudo systemctl restart krillion-bot'      # restart"
