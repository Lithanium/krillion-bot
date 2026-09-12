#!/usr/bin/env bash
# Runs ON the VM (deploy.sh calls it over ssh). Idempotent.
# Installs python + venv, deps, the systemd unit, then (re)starts the bot.
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/krillion-bot}"
SERVICE=krillion-bot
RUN_USER="$(id -un)"

cd "$APP_DIR"

# The 1 GB Always Free micro shape has no swap; dnf/apt metadata + pip can OOM it
# hard enough that even ssh stops answering. Give it a swapfile first.
if [ -z "$(swapon --show --noheadings)" ]; then
    echo "==> Adding 2G swapfile"
    sudo fallocate -l 2G /swapfile 2>/dev/null \
        || sudo dd if=/dev/zero of=/swapfile bs=1M count=2048 status=none
    sudo chmod 600 /swapfile
    sudo mkswap -q /swapfile
    sudo swapon /swapfile
    grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

echo "==> Installing system packages"
if command -v apt-get >/dev/null 2>&1; then
    # Ubuntu / Debian (Canonical Ubuntu images on Oracle Cloud)
    PY=python3
    if ! "$PY" -m venv --help >/dev/null 2>&1 || ! "$PY" -m pip --version >/dev/null 2>&1; then
        sudo DEBIAN_FRONTEND=noninteractive nice -n 19 apt-get update -qq
        sudo DEBIAN_FRONTEND=noninteractive nice -n 19 apt-get install -y -qq --no-install-recommends \
            python3 python3-venv python3-pip >/dev/null
    fi
elif command -v dnf >/dev/null 2>&1; then
    # Oracle Linux 8/9 - system python is too old, use 3.11
    PY=python3.11
    if ! command -v "$PY" >/dev/null 2>&1; then
        # Only the two repos that carry python; the default set (UEK, ksplice, oci_included, ...)
        # pulls hundreds of MB of metadata into RAM on every run.
        OL="$(. /etc/os-release && echo "${VERSION_ID%%.*}")"
        sudo nice -n 19 dnf install -y -q --nodocs --setopt=install_weak_deps=False \
            --disablerepo='*' --enablerepo="ol${OL}_baseos_latest,ol${OL}_appstream" \
            python3.11 python3.11-pip >/dev/null
    fi
else
    echo "Unsupported distro: need apt-get or dnf" >&2
    exit 1
fi

echo "==> Creating virtualenv + installing"
if [ ! -x .venv/bin/python ]; then
    "$PY" -m venv .venv
fi
nice -n 19 .venv/bin/pip install --quiet --no-cache-dir .
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
