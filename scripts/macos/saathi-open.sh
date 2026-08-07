#!/usr/bin/env bash
# M57 macOS shortcut entry point. Stable target for an Option+Command+B binding.
# Delegates to the safe launcher: opens SaathiOS, starting it first if needed.
# Localhost-only. No secrets. Does not keep Terminal focused.
set -euo pipefail
for c in "$HOME/.local/bin/saathi-local" "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/bin/saathi-local"; do
  if [ -x "$c" ]; then exec "$c" open; fi
done
echo "saathi-local not found" >&2; exit 1
