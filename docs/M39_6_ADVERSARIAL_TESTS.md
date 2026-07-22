# M39.6 — Security & Adversarial Test Expansion

**Status:** ADVERSARIAL_COVERAGE_EXPANDED (test-only; synthetic credentials only).
**Series:** PRE-M40 offline readiness (`docs/PRE_M40_OFFLINE_READINESS_PLAN.md`).
**Tests:** `tests/test_m39_6_adversarial.py` — 37 passed.
**Modules touched:** none (test-only; no production code changed).

## Purpose

Prove the M39 + M39.1–M39.5 surfaces fail closed against adversarial input, using
synthetic credentials only. No new subsystem; no production code change.

## Attack vectors covered

| Vector | Assertion |
|--------|-----------|
| raw-secret injection | every locator entry point rejects `ghp_`/`gho_`/`Bearer`/`raw:` shapes |
| env value-vs-name confusion | token-shaped env var name rejected; value never read into output |
| command injection | keychain `_parse` treats shell metacharacters as literal service name |
| endpoint escape / traversal / SSRF | `/repos`, `../../etc/passwd`, `169.254.169.254`, `/user/../admin` not allowlisted |
| method escape | POST/PUT/DELETE/PATCH rejected in approval records |
| provider substitution | non-`github_meta` provider rejected (checklist + approval) |
| scope / rollout escalation | rollout > 5% rejected |
| canary escalation | decision hardcodes `grants_canary=false` even with forged "live PASSED" inputs |
| kill-switch bypass | `SAATHI_M39_KILL_SWITCH=1` forces preflight block |
| budget bypass | per-session budget outside 1..3 rejected |
| unsafe defaults | deployment config with live-flag on / rollout ON / canary GRANTED rejected |
| evidence tampering | audit events with injected secret / leaking reason rejected |
| exception/output leakage | error messages never carry the synthetic token |
| redaction | diagnostics never surface a present env secret |
| non-live guarantee | fault simulation matrix stays `no_live_network` |

## Authority state (unchanged)

CANARY / ACTIVE / rollout / production / write = **NOT GRANTED**. Trading Guardian
**UNENGAGED**.

## Reproduce

```bash
python -m pytest tests/test_m39_6_adversarial.py -q
```
