#!/usr/bin/env bash
# Compatibility entrypoint for older launchd configuration. Process ownership,
# readiness, loopback binding, and logs are delegated to the canonical SaathiOS
# localhost manager.
set -euo pipefail

SCRIPT_DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
exec "$SCRIPT_DIR/../bin/saathi-local" start
