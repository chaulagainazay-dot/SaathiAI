#!/bin/bash
# Baadar Oracle Cloud Setup Script
# Run this once on a fresh Ubuntu 22.04 VM as ubuntu user
# Usage: bash oracle-setup.sh

set -e

echo "=== Baadar Oracle Cloud Setup ==="

# 1. System packages
sudo apt-get update -y
sudo apt-get install -y python3.11 python3.11-venv python3-pip git nginx certbot python3-certbot-nginx ffmpeg

# 2. Clone repo
cd ~
if [ ! -d "SaathiAI" ]; then
  git clone https://github.com/chaulagainazay-dot/SaathiAI.git
fi
cd SaathiAI

# 3. Python venv + deps
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 4. Create .env from template (user fills in secrets)
if [ ! -f ".env" ]; then
  cp .env.example .env 2>/dev/null || touch .env
  echo ">>> IMPORTANT: fill in your secrets in ~/SaathiAI/.env"
fi

# 5. Create data dir for SQLite
mkdir -p data

# 6. Systemd service so Baadar runs 24/7 and auto-restarts
sudo tee /etc/systemd/system/baadar.service > /dev/null <<EOF
[Unit]
Description=Baadar AI Server
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/SaathiAI
EnvironmentFile=/home/ubuntu/SaathiAI/.env
ExecStart=/home/ubuntu/SaathiAI/venv/bin/uvicorn saathi.server:app --host 127.0.0.1 --port 8765
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable baadar
sudo systemctl start baadar

# 7. Nginx reverse proxy (port 80 → 8765)
sudo tee /etc/nginx/sites-available/baadar > /dev/null <<'EOF'
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:8765;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        client_max_body_size 50M;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/baadar /etc/nginx/sites-enabled/baadar
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl restart nginx

# 8. Open firewall ports
sudo iptables -I INPUT -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT -p tcp --dport 443 -j ACCEPT

echo ""
echo "=== Done! ==="
echo "Baadar is running at http://$(curl -s ifconfig.me)"
echo "Dashboard: http://$(curl -s ifconfig.me)/dashboard.html"
echo ""
echo "Next steps:"
echo "1. Fill in secrets: nano ~/SaathiAI/.env"
echo "2. Add firebase key: nano ~/SaathiAI/firebase-admin.json"
echo "3. Check status: sudo systemctl status baadar"
echo "4. View logs: sudo journalctl -u baadar -f"
