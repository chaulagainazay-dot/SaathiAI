# M45 — Operator Guide

> **M45 authorizes nothing to run.** Readiness is advisory.

## CLI

```bash
python -m saathi.credentials.cli m45-status
python -m saathi.credentials.cli m45-create-snapshot --mode observe --percent 1 --max-percent 5 --out-file /tmp/snap.json
python -m saathi.credentials.cli m45-validate-snapshot --snapshot-file /tmp/snap.json
python -m saathi.credentials.cli m45-verify-snapshot --snapshot-file /tmp/snap.json
python -m saathi.credentials.cli m45-check-request-readiness \
  --request-file /tmp/req.json --snapshot-file /tmp/snap.json
python -m saathi.credentials.cli m45-list-snapshots
python -m saathi.credentials.cli m45-show-snapshot <snapshot_id>
python -m saathi.credentials.cli m45-expire-snapshot <snapshot_id>
python -m saathi.credentials.cli m45-invalidate-snapshot <snapshot_id>
python -m saathi.credentials.cli m45-simulate
python -m saathi.credentials.cli m45-emit-evidence
```

Exit codes: `0` ok/advisory-ready, `5` blocked/not-ready, `2` invariant/leak.

## Typical flow

1. Build a signed M44 rollout request (evidence fingerprints from M43/M42).
2. Create an M45 snapshot (`observe` mode) on the intended machine/repo.
3. Validate snapshot integrity and eligibility.
4. Run `m45-check-request-readiness`.
5. If verdict is `BOUNDED_ROLLOUT_READY_FOR_SEPARATE_OPERATOR_AUTHORIZATION`,
   still **do not execute** — obtain a separate operator execution authorization.

## What not to do

- Do not treat readiness as production readiness.
- Do not pass raw credentials on the CLI.
- Do not enable write/deploy/live-network flags.
- There is no M45 execute/deploy command by design.
