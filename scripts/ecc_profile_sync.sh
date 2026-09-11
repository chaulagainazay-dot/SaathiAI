#!/usr/bin/env bash
# Sync the curated SaathiOS ECC profile from the pinned, disabled ecc@ecc plugin cache
# into project-local .claude/{skills,agents,commands,rules}.
#
# Synced content is vendor material and is gitignored. This script plus
# .claude/ecc-profile.json are the committed source of truth.
#
# Usage:
#   scripts/ecc_profile_sync.sh            # sync
#   scripts/ecc_profile_sync.sh --check    # report drift, change nothing
#   scripts/ecc_profile_sync.sh --clean    # remove all synced ECC content
#
# Development plane only. Nothing here grants trading, risk, approval,
# execution, broker, or ledger authority. See docs/engineering/ECC_INTEGRATION.md.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST="$REPO_ROOT/.claude/ecc-profile.json"
DEST="$REPO_ROOT/.claude"

[ -f "$MANIFEST" ] || { echo "missing $MANIFEST" >&2; exit 1; }

VENDOR="$(python3 -c "
import json,os
m=json.load(open('$MANIFEST'))
print(os.path.expanduser(m['vendorRoot']))")"
VERSION="$(python3 -c "import json;print(json.load(open('$MANIFEST'))['eccVersion'])")"

if [ ! -d "$VENDOR" ]; then
  echo "ECC vendor root not found: $VENDOR" >&2
  echo "The ecc@ecc plugin must stay installed (disabled is correct)." >&2
  echo "Reinstall: claude plugin install ecc@ecc --scope project && claude plugin disable ecc@ecc" >&2
  exit 1
fi

MODE="${1:-sync}"

if [ "$MODE" = "--clean" ]; then
  rm -rf "$DEST/skills" "$DEST/agents" "$DEST/commands" "$DEST/rules/ecc"
  echo "removed synced ECC content"
  exit 0
fi

read_list() { python3 -c "import json;print('\n'.join(json.load(open('$MANIFEST'))['$1']))"; }

missing=0
copied=0

sync_one() {  # kind srcpath destpath
  local kind="$1" src="$2" dst="$3"
  if [ ! -e "$src" ]; then
    echo "  MISSING $kind: $(basename "$src")" >&2
    missing=$((missing+1))
    return
  fi
  if [ "$MODE" = "--check" ]; then
    if [ ! -e "$dst" ] || ! diff -rq "$src" "$dst" >/dev/null 2>&1; then
      echo "  DRIFT $kind: $(basename "$src")"
    fi
    return
  fi
  rm -rf "$dst"
  mkdir -p "$(dirname "$dst")"
  cp -R "$src" "$dst"
  copied=$((copied+1))
}

echo "ECC profile sync — vendor $VERSION ($VENDOR)"

[ "$MODE" = "--check" ] || mkdir -p "$DEST/skills" "$DEST/agents" "$DEST/commands" "$DEST/rules/ecc"

while IFS= read -r s; do
  [ -n "$s" ] && sync_one skill "$VENDOR/skills/$s" "$DEST/skills/$s"
done < <(read_list skills)

while IFS= read -r a; do
  [ -n "$a" ] && sync_one agent "$VENDOR/agents/$a.md" "$DEST/agents/$a.md"
done < <(read_list agents)

while IFS= read -r c; do
  [ -n "$c" ] && sync_one command "$VENDOR/commands/$c.md" "$DEST/commands/$c.md"
done < <(read_list commands)

while IFS= read -r r; do
  [ -n "$r" ] && sync_one rules "$VENDOR/rules/$r" "$DEST/rules/ecc/$r"
done < <(read_list rules)

# common/ rule files are ALWAYS-loaded (no `paths:` gate), so only the kept
# subset is synced. See rulesCommonDropped in the manifest for why.
if [ "$MODE" != "--check" ]; then
  mkdir -p "$DEST/rules/ecc/common"
  rm -rf "$DEST/rules/ecc/common"
  mkdir -p "$DEST/rules/ecc/common"
fi
while IFS= read -r r; do
  [ -n "$r" ] && sync_one rule-common "$VENDOR/rules/common/$r.md" "$DEST/rules/ecc/common/$r.md"
done < <(read_list rulesCommonKeep)

if [ "$MODE" = "--check" ]; then
  echo "check complete (missing: $missing)"
else
  echo "synced $copied component(s); missing: $missing"
fi

[ "$missing" -eq 0 ] || exit 2
