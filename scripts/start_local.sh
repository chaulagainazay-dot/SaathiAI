#!/usr/bin/env bash
# Always-on local SaathiAI: FastAPI API (:8765) + SaathiAI OS dashboard (:3100).
# So you can do everything from localhost on the Mac. Loaded by launchd at login.
# CANONICAL LOCAL FRONTEND = http://localhost:3100 (was :3000; retired 2026-09-12
# to end the split-brain where a stale :3000 server served an old build).
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
# Single-origin topology: the browser talks ONLY to this Next origin (:3100).
# Empty NEXT_PUBLIC_* => same-origin relative /api/... , which next.config.mjs
# rewrites proxy to the loopback backend (127.0.0.1:8765). SAATHI_OS_DATA remains
# the multi-host override (set it to an absolute VM URL to restore direct calls).
export NEXT_PUBLIC_SAATHI_API="${SAATHI_OS_DATA-}"
export NEXT_PUBLIC_LOCAL_API=""
# Canonical local frontend port. `npm run start` now honours PORT (package.json
# no longer hard-codes -p), so the Oracle VM keeps its own PORT=3000 while the
# Mac runs the one canonical UI on :3100.
export PORT=3100
export SAATHI_OS_URL="http://localhost:3100"      # API root redirect → local UI
export SAATHI_SELF_BASE="http://127.0.0.1:3100"   # Next server-side self-fetch base
if ! curl -s -o /dev/null http://localhost:3100 2>/dev/null; then
  npm run build >/dev/null 2>&1 || true
  nohup npm run start -- -H 127.0.0.1 >/dev/null 2>&1 &   # localhost-only UI listener on :3100
fi
wait
