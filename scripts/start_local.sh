#!/usr/bin/env bash
# Always-on local SaathiAI: FastAPI API (:8765) + SaathiAI OS dashboard (:3000).
# So you can do everything from localhost on the Mac. Loaded by launchd at login.
set -e
cd "$HOME/SaathiAI"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
export SAATHI_HOST=127.0.0.1   # localhost-only: never bind 0.0.0.0 (LAN) from the launcher

# 1. API
if ! curl -s -o /dev/null http://localhost:8765/api/v1/mission 2>/dev/null; then
  nohup ./.venv/bin/python -m saathi.server > data/local_server.log 2>&1 &
fi

# 2. UI — ONE SOURCE OF TRUTH: data comes from the VM (SAATHI_OS_DATA), while
#    Mac-only capabilities (voice, code-memory) stay on the local API :8765.
cd saathi-os
export NEXT_PUBLIC_SAATHI_API="${SAATHI_OS_DATA:-https://140-245-193-190.nip.io}"
export NEXT_PUBLIC_LOCAL_API="http://localhost:8765"
if ! curl -s -o /dev/null http://localhost:3000 2>/dev/null; then
  npm run build >/dev/null 2>&1 || true
  nohup npm run start -- -H 127.0.0.1 >/dev/null 2>&1 &   # localhost-only UI listener
fi
wait
