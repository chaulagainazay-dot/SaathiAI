# LONG-DURATION-SHADOW-OBSERVATION-1 — epoch 1 opened

**Status: `LONG_DURATION_SHADOW_OBSERVATION_STARTED`.** No evidence verdict is
claimed — the epoch has just begun and elapsed time is the entire point.

Track A runs in its own worktree, `/Users/macbookpro/SaathiAI-observation-epoch-1`,
on branch `observation/epoch-1` **pinned to `78921d75`** so Track B can evolve the
serving runtime without moving the ground under this epoch.

## What an epoch is

A window of **frozen configuration** over which evidence accumulates. That is the
whole idea, and the module exists to protect it: evidence gathered under one
strategy version, cost model or monitoring policy cannot be appended to evidence
gathered under another and still mean anything. Nothing crashes when incompatible
evidence is stitched together — the numbers simply stop meaning what they claim.

## Not a new evidence store

The evidence already has a durable home: the shadow session, its events, fills and
counterfactuals in `ShadowSessionStore`. The manifest records **which
configuration produced which session**, plus checkpoints that point back at it.
Counts are carried so a manifest is readable alone, but nothing is ever
recomputed from them — the session stays the only thing an analysis reads.

Manifests are small atomic JSON documents under `.runtime/observation-epochs/`
(write-temp-then-rename, mode 0600), the same convention the NEPSE directory
snapshots use.

## The live epoch

Two earlier epochs were opened and immediately invalidated, both with **zero
evidence**, and the sequence is worth recording because it proves the
invalidation rule is real rather than decorative.

`epoch-1` was opened at `78921d75`. Committing this observer module then moved
the branch tip, and `verify_provenance` returned `CODE_SHA_CHANGED` — even though
the *observed trading chain* was byte-identical (`git diff 78921d75..HEAD` over
`saathi/platform/tg/` excluding the observer is empty). The rule is deliberately
coarse: it anchors to the SHA of the code actually running, and weakening it to
"only the files I consider material" is how an epoch quietly outlives the
configuration it claims to describe. `epoch-2` met the same fate when this
document was written.

**The operational lesson, now written into the workflow: land every commit on the
observation branch BEFORE opening the live epoch.** An epoch is opened last, and
the branch does not move again while it is open.

| | |
|---|---|
| epoch_id | `epoch-3` |
| provenance fingerprint | recorded in the manifest at open |
| started_at | see manifest |
| mode | **REPLAY** |
| strategy | `btc-mean-reversion@crypto-1-paper-candidate` |
| qualification ref | `45a115c978047e22…` (STRATEGY-CRYPTO-1) |
| dataset | `binance-spot-1d-2018-01-01…2025-12-31 btcusdt/ethusdt @ sha256-0f1290db…` |
| benchmark | `BTC_BUY_AND_HOLD` |
| expected window | 30 days |

**Why REPLAY and not LIVE_PUBLIC.** `LIVE_PUBLIC` is a certified shadow mode, but
no live public feed supervisor is wired into this process — that is Track B's
work. Labelling the epoch `LIVE_PUBLIC` without one would be exactly the false
label the program forbids, so it runs at the highest mode the evidence actually
supports.

Fifteen provenance fields are captured and fingerprinted as a whole, so a restart
or a later process detects drift by comparing one hash rather than remembering
which fields mattered.

## Epoch invalidation

Ten named conditions end an epoch rather than extending it: strategy version,
monitor policy, cost model, fill model, benchmark, execution semantics, data
provenance, PIT boundary, runtime wiring, code SHA. Each is parametrised in the
tests. A cosmetic change — branch name, requalification reference — does not
invalidate; the distinction is explicit rather than incidental.

**This is how Track B is kept from silently corrupting Track A.** If Track B
changes producer or collector versions, `verify_provenance` returns
`RUNTIME_WIRING_CHANGED` and epoch 1 closes as INVALIDATED; a new epoch starts
under the new SHA. Evidence up to that point keeps its meaning — it simply stops
growing.

## The observer cannot touch what it observes

`NO_AUTOMATIC_RETUNING`, `NO_AUTOMATIC_STRATEGY_SWITCHING`,
`NO_AUTOMATIC_LIVE_PROMOTION`, `NO_OBSERVER_EXECUTION_AUTHORITY` — all structural.
An AST test asserts the module defines no `tune`/`retune`/`promote`/
`set_parameter`/`set_threshold`/`switch_strategy`/`adjust`/`optimize`/`calibrate`,
calls no `record_fill`/`submit`/`consume`/`approve`/`set_status`/`force_state`,
and imports no broker, venue, ledger, execution or OMS module. The guarantee is an
absence, so it is checked by parsing for the absence rather than by trusting a
docstring. A DEGRADED verdict is recorded and left alone.

## Failure is evidence too

Checkpoint kinds cover STARTUP, WINDOW, **FAULT**, **RESTART** and EPOCH_CLOSE.
A checkpoint that cannot read the session still records that it happened with the
exception type — losing the checkpoint would lose the fault it was reporting.

## Restart

Proven: resuming yields the same epoch id, session id, start time and checkpoint
count; no duplicate epoch is forked; a DEGRADED health reading survives; and a
resumed epoch still detects configuration drift. No counter resets, no fabricated
HEALTHY on startup.

## Verification

**32 focused tests**, all passing. Ten parametrised invalidation conditions, the
structural no-retuning proof, atomic/0600 manifest writing, path-traversal refusal
on epoch ids, and restart continuity.

## Current elapsed evidence

**None.** The epoch opens with zero events, zero fills and zero closed trades.
Any performance claim at this point would be fabricated.

## Limitations carried on the manifest

- `NO_LIVE_TRADING`; no real orders are ever sent
- no private broker or exchange account
- REPLAY mode: no live public feed supervisor in this process (Track B)
- MARKET_DATA / PROVIDER / APPROVAL report INSUFFICIENT_EVIDENCE until Track B
- spent TEST windows from crypto-1 are not reusable and are not reopened
- **strategy ceiling remains `PAPER_CANDIDATE`; this epoch does not promote it**
- no elapsed-time evidence exists at epoch start
- supersedes `epoch-1` and `epoch-2`, both INVALIDATED by `CODE_SHA_CHANGED` with
  zero evidence recorded
