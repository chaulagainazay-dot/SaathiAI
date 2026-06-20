#!/bin/bash
# Baadar startup wrapper — prevents Mac sleep while running
# caffeinate -i = prevent idle sleep (display can still dim/off)
# caffeinate -s = prevent system sleep entirely (even on AC power)

cd /Users/macbookpro/SaathiAI

# Source environment if .env exists
if [ -f .env ]; then
  set -a; source .env; set +a
fi

exec /usr/bin/caffeinate -i \
  /Users/macbookpro/SaathiAI/.venv/bin/python -m saathi.server
