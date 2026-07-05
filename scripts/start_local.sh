#!/usr/bin/env bash
# Always-on local SaathiAI: FastAPI API (:8765) + SaathiAI OS dashboard (:3000).
# So you can do everything from localhost on the Mac. Loaded by launchd at login.
set -e
cd "$HOME/SaathiAI"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

# 1. API
if ! curl -s -o /dev/null http://localhost:8765/api/v1/mission 2>/dev/null; then
  nohup ./.venv/bin/python -m saathi.server > data/local_server.log 2>&1 &
fi

# 2. UI (prod build → start; falls back to dev)
cd saathi-os
if ! curl -s -o /dev/null http://localhost:3000 2>/dev/null; then
  [ -d .next ] || NEXT_PUBLIC_SAATHI_API="" npm run build >/dev/null 2>&1 || true
  NEXT_PUBLIC_SAATHI_API="" nohup npm run start >/dev/null 2>&1 &
fi
wait
