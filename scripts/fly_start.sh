#!/bin/bash
# Fly.io startup script
# Writes secret env vars → files, then starts Baadar

set -e
cd /app

echo "=== Baadar cloud startup ==="

# 1. Make sure data dir exists (backed by Fly volume)
mkdir -p data

# 2. Write connections.json from secret (FB/IG tokens)
if [ -n "$CONNECTIONS_JSON" ]; then
  echo "$CONNECTIONS_JSON" > data/connections.json
  echo "✅ connections.json written from secret"
elif [ ! -f data/connections.json ]; then
  echo '{"facebook":{"connected":false},"instagram":{"connected":false}}' > data/connections.json
  echo "⚠️  connections.json — placeholder (set CONNECTIONS_JSON secret)"
fi

# 3. Write firebase-admin.json from secret
if [ -n "$FIREBASE_ADMIN_JSON" ]; then
  echo "$FIREBASE_ADMIN_JSON" > firebase-admin.json
  echo "✅ firebase-admin.json written from secret"
fi

# 4. Write .env from individual secrets (already available as env vars — nothing to do)
echo "✅ Env vars loaded from Fly secrets"

echo "=== Starting Baadar server ==="
exec python -m saathi.server
