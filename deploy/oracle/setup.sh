#!/usr/bin/env bash
# SaathiAI · Oracle Cloud (Always Free ARM) one-shot deploy — Ubuntu 24.04.
# Usage on the VM:
#   git clone <your repo> ~/SaathiAI    (or rsync it up)
#   scp your local .env to ~/SaathiAI/.env
#   bash ~/SaathiAI/deploy/oracle/setup.sh [DOMAIN]
# If DOMAIN is omitted, an instant HTTPS domain is derived from the public IP via nip.io.
set -euo pipefail

APP=~/SaathiAI
IP="$(curl -fsS ifconfig.me || curl -fsS https://api.ipify.org)"
DOMAIN="${1:-$(echo "$IP" | tr '.' '-').nip.io}"
echo "▶ Deploying SaathiAI → https://${DOMAIN}  (public IP ${IP})"

# ── 1. system packages ─────────────────────────────────────────────────────
sudo apt-get update -y
sudo apt-get install -y build-essential git curl software-properties-common \
    ffmpeg libportaudio2 ca-certificates gnupg debian-keyring debian-archive-keyring apt-transport-https
# Python 3.12 (SaathiAI needs >=3.11; Ubuntu 22.04 ships 3.10, so use deadsnakes)
if ! command -v python3.12 >/dev/null 2>&1; then
  sudo add-apt-repository -y ppa:deadsnakes/ppa
  sudo apt-get update -y
  sudo apt-get install -y python3.12 python3.12-venv python3.12-dev
fi
PY=python3.12
# Node 20
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs
# Caddy (automatic HTTPS)
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
sudo apt-get update -y && sudo apt-get install -y caddy

# ── 2. Python platform ─────────────────────────────────────────────────────
cd "$APP"
[ -d .venv ] || "$PY" -m venv .venv
./.venv/bin/pip install --upgrade pip wheel
./.venv/bin/pip install -e .
if [ ! -f .env ]; then
  echo "⚠  No .env found — copy your local .env to $APP/.env (keys/tokens), then re-run." ; exit 1
fi

# ── 3. Next.js UI (same-origin API via Caddy → NEXT_PUBLIC_SAATHI_API empty) ─
cd "$APP/saathi-os"
npm ci
NEXT_PUBLIC_SAATHI_API="" npm run build

# ── 4. open host firewall (Oracle Ubuntu images block ports in iptables) ────
sudo iptables -I INPUT -p tcp --dport 80  -m conntrack --ctstate NEW -j ACCEPT || true
sudo iptables -I INPUT -p tcp --dport 443 -m conntrack --ctstate NEW -j ACCEPT || true
sudo bash -c 'command -v netfilter-persistent >/dev/null && netfilter-persistent save || iptables-save > /etc/iptables/rules.v4' || true

# ── 5. services + reverse proxy ────────────────────────────────────────────
sudo cp "$APP/deploy/oracle/saathi-api.service" /etc/systemd/system/
sudo cp "$APP/deploy/oracle/saathi-ui.service"  /etc/systemd/system/
sudo sed "s/SAATHI_DOMAIN/${DOMAIN}/g" "$APP/deploy/oracle/Caddyfile" | sudo tee /etc/caddy/Caddyfile >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now saathi-api saathi-ui
sudo systemctl restart caddy

echo ""
echo "✅ SaathiAI is live:  https://${DOMAIN}"
echo "   Install on Android: open that URL in Chrome → ⋮ → Install app."
echo "   Logs:  journalctl -u saathi-api -f   ·   journalctl -u saathi-ui -f   ·   journalctl -u caddy -f"
echo ""
echo "⚠  Remember (once) in the OCI Console: VCN → Security List → add Ingress"
echo "   0.0.0.0/0  TCP  ports 80 and 443, or Caddy can't obtain a certificate."
