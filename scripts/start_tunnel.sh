#!/bin/bash
# Starts cloudflared tunnel for Baadar and updates TIKTOK_REDIRECT_URI in .env
LOG=/Users/macbookpro/SaathiAI/data/cloudflared.log
ENV=/Users/macbookpro/SaathiAI/.env

# Start tunnel
/opt/homebrew/bin/cloudflared tunnel --url http://localhost:8765 --no-autoupdate > "$LOG" 2>&1 &
CPID=$!

# Wait for URL to appear
for i in $(seq 1 20); do
  sleep 3
  URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG" | tail -1)
  if [ -n "$URL" ]; then
    # Update .env
    sed -i '' "s|TIKTOK_REDIRECT_URI=.*|TIKTOK_REDIRECT_URI=${URL}/api/v1/tiktok/callback|" "$ENV"
    # Restart Baadar to pick up new URL
    launchctl stop com.ajay.saathiai 2>/dev/null
    sleep 3
    launchctl start com.ajay.saathiai 2>/dev/null
    # Notify via Telegram (best-effort)
    curl -s -X POST http://localhost:8765/api/v1/telegram/send \
      -H "X-Saathi-Token: 9278af2af4de585e" \
      -H "Content-Type: application/json" \
      -d "{\"text\":\"🌐 Cloudflare tunnel started\\nTikTok redirect: ${URL}/api/v1/tiktok/callback\\n⚠️ Update this URL in TikTok Developer Console if changed.\"}" 2>/dev/null
    echo "Tunnel URL: $URL"
    break
  fi
done

wait $CPID
