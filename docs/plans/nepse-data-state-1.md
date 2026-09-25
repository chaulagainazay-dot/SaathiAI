# NEPSE-DATA-STATE-1 — durable enrichment, provenance visibility, fallback integrity

Branch `feature/nepse-completion`, from `ae83e3f3` (verified HEAD, clean, in sync).

## The two defects

1. **A backend restart silently downgraded the data.** Sector map 183 → 24, broker
   names 92 → 8. The enrichment is produced by a live browser call whose session is
   memory-resident; when it dies the app falls back to a built-in list. The fallback
   was labelled, but in a caption — far too quiet for a financial surface.
2. **The fallback can render an invalid identity.** `49 null` appeared next to real
   money flows, and the fallback calls broker 45 "Kumari Securities" where the
   verified public source says "Imperial Securities". The fallback is not authority.

Neither is fixed by editing the built-in list. The list being wrong is the point:
what is missing is durable last-known-good state and an explicit authority order.

## Discovery — what already exists (adapt, do not duplicate)

| Concern | Existing contract | Decision |
|---|---|---|
| Per-value quality | `INDICATOR_STATUS` (VALID / DATA_STALE / DATA_CONFLICT / …) | reuse verbatim |
| Source classification | `SOURCE_CLASS` in `lib/nepse/history.js` | reuse |
| Source provenance shape | `NEPSE_RESEARCH_SOURCE` `{id, provider, classification, license, …}` | reuse shape |
| Display state for a degraded feed | `FEED_SOURCE_LABEL` (live / snapshot / unconfigured / blocked / error) | mirror the idiom for directories |
| Runtime state dir | `.runtime/`, `SAATHI_RUNTIME_STATE_DIR` (`saathi/runtime_paths.py`) | reuse the same location |
| Node-side persistence | none — deps are Next/React only, no SQLite binding | atomic JSON snapshot files |

SQLite is canonical on the **Python** side. The enrichment is produced and consumed
entirely in the **Node** layer, and `saathi-os` has no SQLite binding (adding one
would mean `better-sqlite3`, which already warns it does not support this machine's
Node 26). A durable snapshot is a small document written whole, so an atomic
write-temp-then-rename gives the required atomicity without a new dependency or a
Python round-trip. It lands under the canonical `.runtime/` directory.

## State model

Mirrors the `FEED_SOURCE_LABEL` idiom rather than inventing a parallel system:

- `LIVE_ENRICHED` — fetched, validated, provenance known, within freshness policy.
- `CACHED_LAST_VERIFIED` — durable last-known-good, integrity-checked. **Never "live".**
- `INCOMPLETE_FALLBACK` — built-in reference only. Visibly warned, not captioned.
- `UNAVAILABLE` — nothing trustworthy. Show nothing rather than something wrong.

## Authority order (Rule 5)

`LIVE_ENRICHED` > `CACHED_LAST_VERIFIED` > `INCOMPLETE_FALLBACK`. A disagreement
between a higher and a lower tier resolves to the higher tier and is RECORDED as a
conflict (`DATA_CONFLICT`), never merged and never silently dropped. Broker 45 is
the live example.

## Scope boundaries

- No sign-in on the user's behalf. The authenticated final hop stays
  `MANUAL_OPERATOR_VALIDATION_REQUIRED`; the deterministic layers are certified offline.
- Model narration stays `MODEL_NARRATION_E2E_UNVERIFIED`.
- The 13 backend release-gate failures reproduce at `b391a52b`, before this session.
  Out of scope; evidence kept.
- Nothing persisted but normalized public reference data. No cookies, tokens or
  authorization headers, ever.
