# M36 — Operations

## Offline path (default / CI)

```bash
python -m saathi.credentials m36-preflight
python -m saathi.credentials emit-m36-evidence
.venv/bin/python -m pytest tests/test_m36_*.py -q
```

## Live path (operator only)

1. Place disposable PAT in Keychain (see Secret Source Runbook).
2. Qualify account + create M36 authorization with all 8 acks.
3. Set `SAATHI_M36_ALLOW_LIVE_SANDBOX_VERIFICATION=1`.
4. Run session with `--live` and secret **reference** only.
5. On completion: lease revoked locally; manually revoke PAT; attest cleanup.
6. Regenerate sanitized evidence; leak scan; re-run tests.

## If no disposable credential

Complete implementation + offline validation. Report:

`M36 IMPLEMENTATION COMPLETE — REAL SANDBOX SESSION NOT EXERCISED`

with blocker: no operator-supplied disposable sandbox secret reference.
