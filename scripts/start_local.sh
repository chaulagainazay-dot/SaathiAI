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

# 2. UI — ONE SOURCE OF TRUTH: the local canonical backend on :8765.
#
#    This default used to be the Oracle VM, which split SaathiOS across TWO
#    application backends: the browser talked to the VM for all data while the
#    Next server talked to :8765 for governed-browser and NEPSE work. The VM
#    build is older — it has no /api/v1/browser/fetch and no
#    /api/v1/platform/tg/operations/trading-ops — so Central Command's Trading
#    Ops panel was calling a backend that does not serve that route, and the
#    local backend held the operational state (35k evidence records against the
#    VM's 189) that the UI was not reading.
#
#    SAATHI_OS_DATA remains the override: point it at the VM to restore the old
#    topology in one variable. Mac-only capabilities (voice, code-memory) keep
#    their own base so a remote data plane cannot capture the microphone.
cd saathi-os
export NEXT_PUBLIC_SAATHI_API="${SAATHI_OS_DATA:-http://127.0.0.1:8765}"
export NEXT_PUBLIC_LOCAL_API="http://localhost:8765"
if ! curl -s -o /dev/null http://localhost:3000 2>/dev/null; then
  npm run build >/dev/null 2>&1 || true
  nohup npm run start -- -H 127.0.0.1 >/dev/null 2>&1 &   # localhost-only UI listener
fi
wait
