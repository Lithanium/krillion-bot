#!/usr/bin/env bash
# Runs ON the VM (deploy.sh calls it over ssh). Idempotent.
# Installs python + venv, deps, the systemd unit, then (re)starts the bot.
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/krillion-bot}"
SERVICE=krillion-bot
RUN_USER="$(id -un)"

cd "$APP_DIR"

echo "==> Installing system packages"
if command -v apt-get >/dev/null 2>&1; then
    # Ubuntu / Debian (Canonical Ubuntu images on Oracle Cloud)
    sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3 python3-venv python3-pip >/dev/null
    PY=python3
elif command -v dnf >/dev/null 2>&1; then
    # Oracle Linux 8/9 - system python is too old, use 3.11
    sudo dnf install -y -q python3.11 python3.11-pip >/dev/null
    PY=python3.11
else
    echo "Unsupported distro: need apt-get or dnf" >&2
    exit 1
fi

echo "==> Creating virtualenv + installing"
if [ ! -x .venv/bin/python ]; then
    "$PY" -m venv .venv
fi
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet .
mkdir -p data

if [ ! -f .env ]; then
    cp .env.example .env
    echo
    echo "!!  $APP_DIR/.env was created from .env.example."
    echo "!!  Set DISCORD_TOKEN in it, then run:  sudo systemctl restart $SERVICE"
    echo
fi
chmod 600 .env

echo "==> Installing systemd unit"
sed -e "s|__APP_DIR__|$APP_DIR|g" -e "s|__USER__|$RUN_USER|g" \
    deploy/krillion-bot.service | sudo tee /etc/systemd/system/$SERVICE.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable $SERVICE >/dev/null 2>&1

if grep -qE '^DISCORD_TOKEN=.+' .env; then
    echo "==> Restarting $SERVICE"
    sudo systemctl restart $SERVICE
    sleep 3
    sudo systemctl --no-pager --lines=15 status $SERVICE || true
else
    echo "==> DISCORD_TOKEN not set; service enabled but not started."
fi
