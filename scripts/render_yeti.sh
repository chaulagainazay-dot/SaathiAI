#!/usr/bin/env bash
# Render-on-demand: start OmniVoice -> make the talking Yeti -> stop OmniVoice.
# Keeps the Mac light by not leaving the 2.4GB voice model in RAM.
# Usage: scripts/render_yeti.sh ["optional custom script text"]
set -uo pipefail
SAATHI="$HOME/SaathiAI"
OMNI="$HOME/Downloads/OmniVoice-Studio-main"
export PATH="$HOME/.local/bin:$PATH"
SCRIPT_ARG="${1:-}"

started=0
if ! curl -sf -m 2 http://127.0.0.1:3900/health >/dev/null 2>&1; then
  echo "starting OmniVoice voice engine..."
  ( cd "$OMNI" && nohup uv run uvicorn main:app --app-dir backend --host 127.0.0.1 --port 3900 > /tmp/omni-backend.log 2>&1 & )
  started=1
  for i in $(seq 1 40); do sleep 3; curl -sf -m 2 http://127.0.0.1:3900/health >/dev/null 2>&1 && break; done
fi

echo "rendering talking Yeti..."
cd "$SAATHI"
.venv/bin/python -c "import sys, json; from saathi.tools import content_studio as cs; print(json.dumps(cs.make_talking_yeti(sys.argv[1] if len(sys.argv) > 1 else ''), indent=2))" "$SCRIPT_ARG"

if [ "$started" = "1" ]; then
  echo "stopping OmniVoice to free memory..."
  bash "$SAATHI/scripts/stop_heavy.sh" >/dev/null 2>&1
fi
echo "done."
