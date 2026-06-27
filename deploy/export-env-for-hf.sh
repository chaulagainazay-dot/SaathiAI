#!/bin/bash
# Print all .env vars + Firebase JSON for copy-pasting into HF Space secrets
cd "$(dirname "$0")/.."

echo "=== Copy each line below into HF Space Settings → Variables and secrets ==="
echo ""

# .env vars
while IFS= read -r line; do
  [[ "$line" =~ ^#.*$ || -z "$line" ]] && continue
  echo "  $line"
done < .env

echo ""
echo "=== Special secrets (paste as single line) ==="
echo ""
echo "FIREBASE_ADMIN_JSON=$(cat firebase-admin.json | tr -d '\n')"
echo ""
echo "CONNECTIONS_JSON=$(cat data/connections.json 2>/dev/null | tr -d '\n' || echo '{}')"
echo ""
echo "=== Done ==="
