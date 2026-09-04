# TEST-INFRA-2 — Final Certification

## Verdict

**`TEST_INFRA_2_CI_AND_ISOLATION_CERTIFIED_WITH_LIMITATIONS`**

Certified with limitations, not fully, for one honest reason: this milestone
added `SAATHI_EVIDENCE_ROOT` when `saathi/runtime_paths.py` already provided an
overlapping mechanism for an adjacent problem. The duplication is documented,
justified for now, and recorded as the top infra debt item. The program's own
standard warns against exactly this, so it is called out rather than buried.

## Bar

| Requirement | Status |
|---|---|
| Audit tests/stores defaulting into real home directories | **MET** — 44 files, ~30 stores, 0 with overrides |
| Isolate test state | **MET** — HOME redirected session-wide; asserted by test |
| Tests never mutate production/user data | **MET** — `~/.saathi` untouched; asserted by test |
| Investigate tracked evidence files mutated by tests | **MET** — 5 writers found and gated (one by fresh-context review) |
| Deterministic temp-store policy | **MET** — root conftest, before any `saathi` import |
| Wire canonical offline suite into CI | **MET (unverified)** — workflow written; no CI history exists to run it |
| Identify 15 slowest tests | **MET** — captured in `TEST_REPORT.md` |
| Reduce suite runtime | **NOT MET** — 668 s → 644 s incidental; no optimisation attempted |
| Evaluate xdist after isolation | **CORRECTLY DEFERRED** — per-store overrides still absent |

## What was found that was not asked for

A **protection bypass in production code**: `config_protection._home()` compared
an unresolved home against a resolved candidate, so any symlinked `$HOME` made
`~/.claude/settings.json`, `~/.ssh/id_rsa` and `~/.aws/credentials` classify as
UNPROTECTED. Fixed, with regression tests. Details in `SECURITY.md`.

## Authority

Unchanged. Trading regression 294 passed / 0 failed. Full audit in
`AUTHORITY_AUDIT.md`.

```
NO LIVE TRADING · NO REAL BROKER · NO WITHDRAWAL · NO LEVERAGE
NO LLM EXECUTION AUTHORITY · NO TRADINGAGENTS RUNTIME DEPENDENCY
NO ECC RUNTIME DEPENDENCY
```

No market-data provider was contacted. No credential requested or configured.
No network call made.

## Continue / stop decision

**`SAFE_TO_CONTINUE`**

- next step (MD-1, canonical market data contract) is a pure type/contract change — read-only, no provider contact
- authority unchanged
- no new credential privilege
- offline regression green, zero trading regression
- no unresolved high-severity defect

## Next milestone: B1 · MD-1 — Canonical market data contract

Selected because the measured gap is the largest in the program and blocks every
later stage: `grep -rn available_at saathi/ tests/` returns **one hit, and it is
a comment**. The whole codebase is `as_of`-only. That is precisely the look-ahead
defect the TradingAgents evaluation identified and warned against, currently
unfixed here.

MD-1 also resolves the **4 duplicate `AssetClass` enums** and **2 competing quote
models** found in the gap audit, before any provider adapter is built on top of
them.
