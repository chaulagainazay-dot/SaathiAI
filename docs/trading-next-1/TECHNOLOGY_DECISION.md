# TECHNOLOGY_DECISION

## Evaluated references

| Technology | Classification | Role for SaathiOS |
| --- | --- | --- |
| QuantConnect LEAN | **ADAPT** | Event/portfolio accounting patterns; do not import full engine |
| Qlib | **DEFER** | Research/ML infrastructure later |
| vectorbt | **DEFER** | Backtest analytics later |
| Freqtrade | **ADAPT** | Dry-run lifecycle ideas only; not authority |
| TradingAgents | **ADAPT** | Research-agent patterns only; never portfolio mutation |
| Institutional event-sourced ledgers | **ADAPT** | Append-only events + deterministic reducer |
| Full LEAN embed | **REJECT** | Too large; would compete with EG/TG ownership |
| Vendor cloud portfolio API | **REJECT** | Live/network risk; not paper-local |

## Decision

```text
KEEP SaathiOS native implementation
ADAPT LEAN-style event/fill → portfolio accounting concepts
ADAPT event-sourced reducer pattern
DEFER Qlib / vectorbt
REJECT full platform import
```

**Canonical implementation:** `saathi/platform/fund_ledger` (T-NEXT-1).

Rationale: SaathiOS must own authority contracts (TG, EG, approvals, paper-only).
A bounded native ledger with Decimal + FIFO + replay integrates cleanly without
bypassing existing gates.

