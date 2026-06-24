#!/bin/bash
# Run this ONCE after flyctl auth signup to push all secrets to Fly
# Usage: bash scripts/fly_set_secrets.sh

export PATH="/Users/macbookpro/.fly/bin:$PATH"
cd /Users/macbookpro/SaathiAI

echo "=== Setting Fly.io secrets from .env ==="

# Load .env and push each key=value to fly secrets
while IFS= read -r line; do
  # skip comments and empty lines
  [[ "$line" =~ ^#.*$ || -z "$line" ]] && continue
  key="${line%%=*}"
  val="${line#*=}"
  echo "  Setting $key..."
  flyctl secrets set "$key=$val" --stage 2>/dev/null
done < .env

# Push connections.json as a single secret (JSON string)
echo "  Setting CONNECTIONS_JSON..."
CONN=$(cat data/connections.json | tr -d '\n')
flyctl secrets set "CONNECTIONS_JSON=$CONN" --stage

# Push firebase-admin.json as a secret
if [ -f firebase-admin.json ]; then
  echo "  Setting FIREBASE_ADMIN_JSON..."
  FB=$(cat firebase-admin.json | tr -d '\n')
  flyctl secrets set "FIREBASE_ADMIN_JSON=$FB" --stage
fi

# Deploy staged secrets
echo "=== Deploying secrets ==="
flyctl secrets deploy

echo "✅ All secrets set!"
