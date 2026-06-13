#!/usr/bin/env bash
# Free the Mac: stop the OmniVoice backend + any stray video-render jobs.
stop_omni() {
  local pids
  pids=$(pgrep -f "uvicorn main:app --app-dir backend" 2>/dev/null)
  [ -z "$pids" ] && pids=$(lsof -nP -iTCP:3900 -sTCP:LISTEN -t 2>/dev/null)
  if [ -n "$pids" ]; then
    echo "stopping OmniVoice ($pids)"; kill -TERM $pids 2>/dev/null
    sleep 3
    pids=$(lsof -nP -iTCP:3900 -sTCP:LISTEN -t 2>/dev/null)
    [ -n "$pids" ] && { echo "force stop"; kill -9 $pids 2>/dev/null; }
  fi
}
stop_omni
pkill -f "talkingyeti/.*inference.py" 2>/dev/null && echo "stopped stray render(s)"
curl -sf -m 2 http://127.0.0.1:3900/health >/dev/null 2>&1 && echo "⚠ OmniVoice still up" || echo "✅ heavy jobs stopped — Mac freed."
