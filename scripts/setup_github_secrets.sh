#!/bin/bash
# Push all Baadar secrets to GitHub in one shot
# Requires: gh CLI installed (brew install gh) and logged in (gh auth login)
# Usage: bash scripts/setup_github_secrets.sh

set -e
cd /Users/macbookpro/SaathiAI
REPO="chaulagainazay-dot/SaathiAI"

echo "=== Pushing secrets to GitHub: $REPO ==="

# Push each key from .env
while IFS= read -r line; do
  [[ "$line" =~ ^#.*$ || -z "$line" ]] && continue
  key="${line%%=*}"
  val="${line#*=}"
  echo "  Setting $key"
  gh secret set "$key" --body "$val" --repo "$REPO"
done < .env

# Push connections.json as CONNECTIONS_JSON
echo "  Setting CONNECTIONS_JSON"
gh secret set "CONNECTIONS_JSON" \
  --body "$(cat data/connections.json | tr -d '\n')" \
  --repo "$REPO"

# Push firebase-admin.json as FIREBASE_ADMIN_JSON
if [ -f firebase-admin.json ]; then
  echo "  Setting FIREBASE_ADMIN_JSON"
  gh secret set "FIREBASE_ADMIN_JSON" \
    --body "$(cat firebase-admin.json | tr -d '\n')" \
    --repo "$REPO"
fi

# Push latest growth calendar if exists
CAL=$(ls data/growth/strategy_30day_*.json 2>/dev/null | sort | tail -1)
if [ -n "$CAL" ]; then
  echo "  Setting GROWTH_CALENDAR_JSON from $CAL"
  gh secret set "GROWTH_CALENDAR_JSON" \
    --body "$(cat "$CAL" | tr -d '\n')" \
    --repo "$REPO"
fi

echo ""
echo "✅ All secrets pushed to GitHub!"
echo "   Go to: https://github.com/$REPO/settings/secrets/actions"
echo "   to verify."
