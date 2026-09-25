# SaathiOS — Owner NEPSE EOD Import (v1)

**From `df490f1f` (source BLOCKED); Research Surface frozen `b771d761`; Fusion `4d685383`.**
Canonical ingestion of an **owner-supplied official NEPSE EOD export** (`OFFICIAL_DOWNLOAD`).
The owner manually downloads the official file in their own authenticated browser; SaathiOS
parses a **local file only** — no scraping, browser automation, token extraction, Browser Use,
or Agent Reach. Provenance is established (owner attestation) **before** any canonical write.

## Reuse (no duplication)
`MarketDataStore`/`md_bars` (idempotent INSERT OR IGNORE), `MDBar`/`Timeframe`/`MarketDataQuality`,
`instruments.normalize_symbol`/`instrument_id_for`. Added ONLY: additive provenance/point-in-time
tables (`md_owner_import_run`, `md_bar_source`, `md_bar_revision`) because base `md_bars` lacks
`available_at` + artifact provenance (mandatory here). No new bar schema/store/symbol registry/
calendar/provider hierarchy.

## New components
`saathi/platform/market_data/owner_import.py` (importer + `canonical_bar_reader` + `import_health`)
and `nepse_import.py` (operator CLI: `inspect` dry-run / `import --attest-official` / `health`).

## Contract
- **Formats:** CSV (stdlib, no new dep). XLSX/XLS/HTML/JSON-error detected by magic and rejected
  (`INVALID_EXPORT_FORMAT`); no speculative openpyxl dependency.
- **Provenance gate:** canonical write requires `--attest-official` → `OFFICIAL_VERIFIED` /
  `verification_method=OWNER_ATTESTED_OFFICIAL_DOWNLOAD` (recorded; not cryptographic). Without it →
  `PROVENANCE_UNVERIFIED` (dry-run inspect still allowed, zero writes).
- **Artifact identity:** SHA-256 of the raw file; every bar traceable to `artifact_id`/`sha256`/`import_run_id` via `md_bar_source`.
- **Validation:** `high≥max(o,c,l)`, `low≤min(o,c,h)`, prices/volume ≥0; **OHLC never fabricated** (missing O/H/L/C → row rejected, not synthesized from LTP); malformed rows → error report.
- **Symbol resolution:** `normalize_symbol` (raises rather than guessing) → `SYMBOL_UNRESOLVED`; **CSV formula-injection guard** (cells starting `= + - @`/tab → unresolved, never executed).
- **available_at policy:** conservative = **owner retrieval/import time** (`AVAILABLE_AT_CONSERVATIVE_RETRIEVAL_BOUNDARY`), stored in `md_bars.source_epoch` + `md_bar_source.available_at`. Never backdated to `trading_date 00:00`.
- **Point-in-time:** `canonical_bar_reader` exposes `available_at` per bar; nothing is visible before `available_at`.
- **Idempotency:** identical artifact SHA → `ALREADY_IMPORTED` (noop); md_bars PK prevents dup bars.
- **Revision:** same key, changed close, new artifact → `CANONICAL_BAR_REVISION` recorded in `md_bar_revision`; original md_bars value **not silently overwritten**.
- **Canonical write gate:** this importer is the ONLY canonical `md_bars` writer; Research/Agent-Reach/Browser-Use/Catalyst/chat/voice/research_surface import neither `owner_import` nor `insert_bar` (test-enforced).
- **Security:** file-size/row caps; magic-based format check; reads data only (no macros/formulas/external links executed); formula-injection guard.
- **Health:** `import_health` → `NO_CANONICAL_DATA` / `CANONICAL_DATA_AVAILABLE`; labelled `OWNER_MANUAL_IMPORT (not a live feed)`.

## Tests
`tests/test_owner_nepse_import_v1.py` **15**: format detection, dry-run parse, invalid/HTML/xlsx
rejection, OHLC/volume validation, unresolved symbol, hash identity, provenance gate, attested
import, available_at + point-in-time, idempotency, revision detection, catalyst market-reaction
from canonical bars (wiring), canonical write gate, health, formula-injection-as-text. 68-test
regression green; frozen baselines 0 diffs.

## Authority (verified)
`ExecutionGateway.execute`=0, TG trade=0, broker=0, portfolio writes=0, orders/payments/withdrawals=0.
Canonical `md_bars` writes: **only** via this owner-import path. Non-canonical market_data writes: 0.
Agent-Reach non-canonical; Browser Use DEFER.

## Status — software complete, awaiting a real official file
No genuine owner-supplied official NEPSE export has been imported yet, so live import + real
catalyst market-reaction revalidation are pending. **Verdict: SAATHIOS_OWNER_NEPSE_EOD_IMPORT_
IMPLEMENTED_VALIDATION_INCOMPLETE → OWNER_OFFICIAL_NEPSE_EXPORT_REQUIRED.** Fusion stays
`CERTIFIED_WITH_LIMITATIONS`.

### Owner action to complete certification
1. In your normal authenticated browser, open the official NEPSE site (`nepalstock.com`) → **Today's Price** (or a historical price page).
2. Export/Download as **CSV** (not XLSX). Choose a date range that includes the current ResearchEvent symbols (UMRH, MBL, PMHPL, SBL, …) around their event dates if a historical export is available; otherwise today's Today's-Price CSV.
3. Save it locally, e.g. `~/Downloads/nepse_price.csv`.
4. Inspect (dry run, no writes):
   `python -m saathi.platform.market_data.nepse_import inspect ~/Downloads/nepse_price.csv`
   (add `--trading-date YYYY-MM-DD` if the export has no date column).
5. If it looks right, import (attesting official origin):
   `python -m saathi.platform.market_data.nepse_import import ~/Downloads/nepse_price.csv --attest-official`
Never share your NEPSE password, cookie, or token — SaathiOS reads only the file you saved.

## Next milestone
After a real import: run the catalyst market-reaction + look-ahead gates on real canonical bars;
if they pass, evaluate upgrading Fusion toward full certification (retrospective reaction vs
historical knowledge-time replay assessed separately, per the availability caveat).
