# NEPSE-1 — Instrument Master and Portfolio Import

## Source of the requirement

A teardown of `nepseportfoliotracker.app` (artifact "NEPSE Tracker Teardown",
walked 2026-08-30) documenting nine screens and, in its closing section, the
seven backend requirements those screens sit on. This milestone builds the two
that are **unblocked**: instrument identity and file-based import.

The teardown's own conclusion is the reason to start here:

> *"File parsers, not an API integration. The import path reads Meroshare CSV,
> TMS Excel, and Nepal Share CSV/TSV — three fixed schemas to parse, not a live
> brokerage connection. That's the realistic starting point before anyone
> attempts real broker integration."*

## What was built

`saathi/platform/nepse/`

| Module | Contents |
|---|---|
| `instruments.py` | `NepseInstrument`, `NepseSector` (15 sectors), `normalize_symbol`, `instrument_id_for`, `sector_from_code` |
| `importers/__init__.py` | `ImportFormat`, `ImportedPosition`, `RejectedRow`, `ImportResult`, `detect_format`, `parse_holdings` |

## What was deliberately NOT built

**No second portfolio store.** The teardown describes total investment, current
value and receivable as derived from a transaction log — which is exactly what
the Canonical Fund Ledger already is (event-sourced, `record_fill`,
`get_positions`, `get_nav`, `get_pnl`, `snapshot`). Import produces a *proposal*;
the ledger stays the sole books authority. Building a parallel portfolio would
have violated the anti-duplication rule and split the accounting truth.

## NEPSE conventions, stated explicitly

US and crypto defaults are wrong here, so they are encoded rather than inherited:

| Property | Value |
|---|---|
| Venue / currency | `NEPSE` / `NPR` |
| Lot size | 10 (round lot) |
| Tick size | 0.10 |
| Price precision | 2 |
| Quantity precision | **0 — whole shares only** |
| Timezone | `Asia/Kathmandu` |
| Calendar | `NEPSE` |

## Identity

`instrument_id = "NEPSE:<SYMBOL>"`. Provider symbols never travel inside
SaathiOS; they normalise through the master first. `nabil`, `NEPSE:NABIL`,
`NABIL.N`, and `N A B I L` all resolve to one identity. An unparseable symbol
**raises** rather than degrading into some other real security.

Venue qualification is what keeps NEPSE and crypto identities disjoint — a bare
`BTC` in a NEPSE file becomes `NEPSE:BTC`, never a crypto pair.

## Import trust model

An uploaded spreadsheet is untrusted input, not a trusted schema.

1. **Nothing is silently lost.** `len(positions) + len(rejected) == rows_seen`
   is a tested invariant. Rejected rows keep their reason and their original
   text for the operator.
2. **Nothing is guessed.** An unrecognised header returns `UNKNOWN` with every
   row rejected — loudly wrong beats quietly wrong. A negative quantity is
   rejected because NEPSE is long-only.
3. **Cell content cannot become structure.** Symbols normalise through a
   `[^A-Z0-9]` strip, so a formula-injection payload (`=cmd|'/c calc'!A1`)
   cannot survive into an instrument identity.
4. **Duplicates are surfaced, not merged.** Two rows for one symbol are kept
   separate and reported, because silently summing them is a guess about intent.

## Authority

The package holds no execution, approval, risk, or ledger-mutation authority,
and performs no network I/O. Enforced by test: `ImportResult` exposes no
`commit`/`apply`/`post`/`save`, the importer module imports nothing from
`fund_ledger`, and neither module references `requests`/`httpx`/`urllib`/
`socket`/`aiohttp`.
