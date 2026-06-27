#!/bin/bash
# Get Firebase JSON as a single line for Koyeb FIREBASE_CREDENTIALS_JSON env var
# Run from ~/SaathiAI or update the path below

set -e

FIREBASE_FILE="${HOME}/SaathiAI/firebase-admin.json"

if [ ! -f "$FIREBASE_FILE" ]; then
    echo "ERROR: Firebase credentials file not found at $FIREBASE_FILE"
    echo "Make sure you have downloaded firebase-admin.json from Firebase Console"
    exit 1
fi

echo "=========================================="
echo "Firebase JSON for Koyeb"
echo "=========================================="
echo ""
echo "Copy the entire output below (including quotes):"
echo ""

python3 -c "import json; d=json.load(open('$FIREBASE_FILE')); print(json.dumps(d))"

echo ""
echo "=========================================="
echo "How to use:"
echo "1. Select all (Cmd+A)"
echo "2. Copy (Cmd+C)"
echo "3. Go to Koyeb dashboard → Environment"
echo "4. Add env var: FIREBASE_CREDENTIALS_JSON = (paste here)"
echo "=========================================="
