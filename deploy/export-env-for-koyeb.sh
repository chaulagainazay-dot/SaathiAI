#!/bin/bash
# Export all env vars from .env in a format easy to paste into Koyeb dashboard
# Run from ~/SaathiAI

set -e

ENV_FILE="${HOME}/SaathiAI/.env"
FIREBASE_FILE="${HOME}/SaathiAI/firebase-admin.json"

if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: .env file not found at $ENV_FILE"
    exit 1
fi

echo "==========================================="
echo "Koyeb Environment Variables"
echo "==========================================="
echo ""
echo "Copy each line below into Koyeb Settings → Environment:"
echo ""

# Read .env and print non-comment, non-empty lines
while IFS= read -r line; do
    # Skip comments and empty lines
    [[ "$line" =~ ^#.*$ ]] && continue
    [[ -z "$line" ]] && continue
    # Print the line
    echo "$line"
done < "$ENV_FILE"

echo ""

# Add Firebase JSON if available
if [ -f "$FIREBASE_FILE" ]; then
    FIREBASE_JSON=$(python3 -c "import json; d=json.load(open('$FIREBASE_FILE')); print(json.dumps(d))" 2>/dev/null)
    echo "FIREBASE_CREDENTIALS_JSON=$FIREBASE_JSON"
else
    echo "FIREBASE_CREDENTIALS_JSON=(ERROR: firebase-admin.json not found)"
fi

echo ""
echo "==========================================="
echo "How to paste into Koyeb:"
echo "==========================================="
echo "1. Run this script: bash deploy/export-env-for-koyeb.sh"
echo "2. Copy the output"
echo "3. Go to Koyeb dashboard → Your app → Settings → Environment"
echo "4. For each line: KEY=VALUE → paste into form"
echo "5. Click 'Save' → 'Redeploy'"
echo ""
echo "Or manually export individual vars:"
echo "  grep GROQ_API_KEY ~/.env"
echo "  grep FIREBASE_CREDENTIALS_JSON ~/.env"
echo "etc."
echo "==========================================="
