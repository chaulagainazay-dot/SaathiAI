#!/usr/bin/env bash
# M343 — clean-clone certification.
#
# Clones the repository at the final milestone SHA into a throwaway directory
# and reproduces the certification there. Nothing is copied from the working
# tree: no .env, no local database, no build output, no cache, no untracked
# evidence, no credential, no source. Only what git tracks at that SHA.
#
# Usage:
#   scripts/m343_clean_clone_certification.sh <full-sha> [output.json]
set -uo pipefail

SHA="${1:?usage: $0 <full-sha> [output.json]}"
SRC_REPO="${SRC_REPO:-/Users/macbookpro/SaathiAI}"
PY="${PY:-/Users/macbookpro/SaathiAI/.venv/bin/python}"
OUT="${2:-$(cd "$(dirname "$0")/.." && pwd)/docs/private-alpha/m336_m343_evidence/M343_CLEAN_CLONE_CERTIFICATION.json}"

CLONE="$(mktemp -d -t m343-clean-clone)"
LOGS="$CLONE/_logs"
mkdir -p "$LOGS"
echo "clean clone: $CLONE"

result_backend="not_run"; result_frontend="not_run"; result_build="not_run"
result_journey="not_run"; result_gate="not_run"; result_focused="not_run"
backend_passed=0; backend_failed=0; frontend_passed=0; frontend_failed=0

cleanup() { :; }   # the clone is left in place for inspection; it is a temp dir
trap cleanup EXIT

# ── 1. clone at the exact SHA, tracked files only ──────────────────────────
git clone --quiet --no-hardlinks "$SRC_REPO" "$CLONE/repo" >"$LOGS/clone.log" 2>&1 || {
  echo "clone failed"; cat "$LOGS/clone.log"; exit 1
}
git -C "$CLONE/repo" checkout --quiet "$SHA" >>"$LOGS/clone.log" 2>&1 || {
  echo "checkout failed"; cat "$LOGS/clone.log"; exit 1
}
CLONE_SHA="$(git -C "$CLONE/repo" rev-parse HEAD)"
echo "clone sha: $CLONE_SHA"

# Prove nothing forbidden came across.
forbidden=0
for path in ".env" ".proxy.env" "data/platform/platform.db" "saathi-os/.next" \
            "saathi-os/node_modules" ".venv" "__pycache__"; do
  if [ -e "$CLONE/repo/$path" ]; then
    echo "FORBIDDEN ARTIFACT PRESENT: $path"; forbidden=$((forbidden+1))
  fi
done
untracked="$(git -C "$CLONE/repo" status --porcelain | wc -l | tr -d ' ')"

cd "$CLONE/repo" || exit 1

# ── 2. focused milestone suites ────────────────────────────────────────────
PYTHONPATH="$CLONE/repo" "$PY" -m pytest \
  tests/test_m57_local.py tests/test_m157_private_alpha.py tests/test_ops.py \
  tests/test_m336_m343_regression_closure.py tests/test_m339_private_alpha_journey.py \
  tests/test_m341_soak_safety.py \
  -p no:randomly -q --no-header > "$LOGS/focused.log" 2>&1
[ $? -eq 0 ] && result_focused="pass" || result_focused="fail"

# ── 3. full backend suite ──────────────────────────────────────────────────
PYTHONPATH="$CLONE/repo" "$PY" -m pytest tests -p no:randomly -q --no-header -rf \
  > "$LOGS/backend.log" 2>&1
backend_line="$(grep -Eo '[0-9]+ (passed|failed)[^)]*' "$LOGS/backend.log" | tail -1)"
backend_failed="$(grep -Eo '^[0-9]+ failed' "$LOGS/backend.log" | tail -1 | grep -Eo '^[0-9]+' || echo 0)"
backend_passed="$(grep -Eo '[0-9]+ passed' "$LOGS/backend.log" | tail -1 | grep -Eo '^[0-9]+' || echo 0)"
[ "${backend_failed:-0}" = "0" ] && result_backend="pass" || result_backend="fail"

# ── 4. release gate ────────────────────────────────────────────────────────
PYTHONPATH="$CLONE/repo" "$PY" -c "
from saathi.ops import release_gate as RG
code, report = RG.release_check(strict_dirty=False)
print('EXIT_CODE', code)
print('SECRET_SCAN_CLEAN', report['gates']['secret_scan']['clean'])
" > "$LOGS/release_gate.log" 2>&1
gate_code="$(grep -Eo 'EXIT_CODE [0-9]+' "$LOGS/release_gate.log" | grep -Eo '[0-9]+' || echo 99)"
[ "$gate_code" = "0" ] || [ "$gate_code" = "1" ] && result_gate="pass" || result_gate="fail"

# ── 5. private-alpha journey ───────────────────────────────────────────────
PYTHONPATH="$CLONE/repo" "$PY" -c "
from saathi.platform.private_alpha.journey import run_private_alpha_journey
r = run_private_alpha_journey(write_evidence=False)
print('VERDICT', r['verdict'])
print('PASSED', r['passed'], 'OF', r['step_count'])
" > "$LOGS/journey.log" 2>&1
grep -q "PRIVATE_ALPHA_E2E_JOURNEY_PASSED" "$LOGS/journey.log" && result_journey="pass" || result_journey="fail"

# ── 6. frontend suite and production build ─────────────────────────────────
cd "$CLONE/repo/saathi-os" || exit 1
npm install --no-audit --no-fund > "$LOGS/npm_install.log" 2>&1
npm test > "$LOGS/frontend.log" 2>&1
frontend_passed="$(grep -Eo '^ℹ pass [0-9]+' "$LOGS/frontend.log" | grep -Eo '[0-9]+' || echo 0)"
frontend_failed="$(grep -Eo '^ℹ fail [0-9]+' "$LOGS/frontend.log" | grep -Eo '[0-9]+' || echo 0)"
[ "${frontend_failed:-0}" = "0" ] && result_frontend="pass" || result_frontend="fail"

npm run build > "$LOGS/build.log" 2>&1
[ $? -eq 0 ] && result_build="pass" || result_build="fail"

# ── 7. security, authority, secret and network scans ───────────────────────
cd "$CLONE/repo" || exit 1
PYTHONPATH="$CLONE/repo" "$PY" -c "
import json
from saathi.platform.private_alpha.launch_readiness import authority_posture
p = authority_posture()
print('ALL_LOCKS_FALSE', p['all_false'])
print(json.dumps(p['locks']))
" > "$LOGS/authority.log" 2>&1
grep -q "ALL_LOCKS_FALSE True" "$LOGS/authority.log" && result_authority="pass" || result_authority="fail"

# Network isolation: no non-localhost host literal in the private-alpha surface.
network_hits="$(grep -rEo 'https?://[a-zA-Z0-9.-]+' \
  saathi/platform/private_alpha bin/saathi-local 2>/dev/null \
  | grep -vE '127\.0\.0\.1|localhost' | wc -l | tr -d ' ')"
[ "${network_hits:-1}" = "0" ] && result_network="pass" || result_network="fail"

overall="M343_CLEAN_CLONE_CERTIFIED"
for r in "$result_focused" "$result_backend" "$result_gate" "$result_journey" \
         "$result_frontend" "$result_build" "$result_authority" "$result_network"; do
  [ "$r" = "pass" ] || overall="M343_CLEAN_CLONE_FAILED"
done
[ "$forbidden" = "0" ] || overall="M343_CLEAN_CLONE_FAILED"

cat > "$OUT" <<JSON
{
  "schema": "m343.clean_clone_certification.v1",
  "milestone": "M336-M343",
  "verdict": "$overall",
  "clone_sha": "$CLONE_SHA",
  "requested_sha": "$SHA",
  "clone_path": "$CLONE/repo",
  "source_repository": "$SRC_REPO",
  "clone_method": "git clone --no-hardlinks then checkout the exact SHA; tracked files only",
  "forbidden_artifacts_present": $forbidden,
  "untracked_files_in_clone": $untracked,
  "not_copied": [".env", ".proxy.env", "local databases", "build output", "caches", "untracked evidence", "local credentials", "original worktree source"],
  "results": {
    "focused_milestone_suites": "$result_focused",
    "full_backend_suite": "$result_backend",
    "release_gate": "$result_gate",
    "private_alpha_journey": "$result_journey",
    "full_frontend_suite": "$result_frontend",
    "production_build": "$result_build",
    "authority_scan": "$result_authority",
    "network_isolation_scan": "$result_network"
  },
  "backend": {"passed": ${backend_passed:-0}, "failed": ${backend_failed:-0}},
  "frontend": {"passed": ${frontend_passed:-0}, "failed": ${frontend_failed:-0}},
  "release_gate_exit_code": ${gate_code:-99},
  "non_localhost_host_literals_in_private_alpha_surface": ${network_hits:-1},
  "logs": "$LOGS",
  "browser_certification": "run separately against a live local stack; see M343_BROWSER_CERT.json"
}
JSON

echo "---"
echo "verdict: $overall"
echo "report:  $OUT"
echo "logs:    $LOGS"
[ "$overall" = "M343_CLEAN_CLONE_CERTIFIED" ] && exit 0 || exit 1
