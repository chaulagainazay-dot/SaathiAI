# Look-Ahead / Data-Leakage Audit (mandatory phase)

Target: TradingAgents `a33fd4c` (v0.3.1 line). Compared against SaathiOS
`market_data` bias controls.

## LOOKAHEAD_PROTECTION_SCORE: **6 / 10**

Good on prices and news. **Materially leaky on fundamentals.** Protection is
per-call-site rather than architectural, which is why the same class of bug has
recurred across releases (#475 in 0.2.x, #1115 in 0.3.1).

## What is protected, and how

| Surface | Mechanism | Verdict |
|---|---|---|
| OHLCV / prices | `market_data_validator._verified_rows()` re-applies `df[df["Date"] <= curr_date]` **defensively even though the loader already filters** — belt and braces | **STRONG** |
| Stale OHLCV | Explicit stale-data rejection guard (`test_yfinance_stale_ohlcv_guard.py`) | **STRONG** |
| News windows | `yfinance_news._in_news_window(pub_date, start, end)` — upper bound exclusive, timezone-aware conversion (not truncation), and **undated articles excluded in backtest but kept in live** | **STRONG** — this nuance is better than most research code |
| Technical indicators | `stockstats_utils` loads OHLCV through the same date-bounded loader | **ADEQUATE** |
| Alpha Vantage CSV series | `_filter_csv_by_date_range(csv, start, end)` | **ADEQUATE** |
| Alpha Vantage fundamentals | `_filter_reports_by_date()` — added in v0.3.1 because the payload is a JSON *string* and the previous dict-only guard silently skipped filtering | **WEAK — see below** |
| yfinance financials | `filter_financials_by_date()` drops statement columns after `curr_date` | **WEAK — see below** |
| Company OVERVIEW | **none** | **BROKEN — see below** |

## Defect 1 — fiscal-period filtering ignores filing lag (HIGH)

`dataflows/alpha_vantage_fundamentals.py`:

```python
payload[key] = [
    r for r in payload[key]
    if r.get("fiscalDateEnding", "") <= curr_date
]
```

`fiscalDateEnding` is the **period end**, not the **publication date**. A quarter
ending 2026-03-31 is typically filed 4–8 weeks later. Analysing 2026-04-10 with
this filter exposes Q1 figures roughly a month before they were public.

`stockstats_utils.filter_financials_by_date()` has the identical flaw: it filters
yfinance statement columns by fiscal period end.

Impact: every fundamentals-driven backtest inherits a 30–75 day forward-looking
information advantage. This is the single most damaging class of look-ahead in
quantitative research, because it looks correct and produces optimistic results.

## Defect 2 — company OVERVIEW is entirely unfiltered (HIGH)

```python
def get_fundamentals(ticker: str, curr_date: str = None) -> str:
    """... curr_date (str): Current date you are trading at (not used for Alpha Vantage)"""
    return _make_api_request("OVERVIEW", params)
```

The docstring states plainly that `curr_date` is not used. `OVERVIEW` returns
**today's** PE, market cap, margins, and analyst target price. `get_fundamentals`
is exported as an analyst tool (`agents/utils/agent_utils.py`, routed via
`fundamental_data_tools.py`), so a historical run receives present-day valuation
data. That is unbounded look-ahead, not a lag.

## Defect 3 — no point-in-time / vintage handling (MEDIUM)

Nothing anywhere handles restatements, revisions, or as-reported vs as-restated
values. Macro series from FRED are revised routinely; the code fetches the
current vintage. There is no concept of "what the number was believed to be on
date T".

## Defect 4 — protection is per-call-site (MEDIUM, structural)

Every provider function applies its own cutoff. There is no chokepoint that a new
data source must pass through. History confirms the failure mode: the
Alpha Vantage filter existed but did not run for a full release because of a type
mismatch, and nothing detected it structurally — only a user report (#1115) did.

## What SaathiOS already does better

`saathi/platform/tg/market_data/` contains, as dedicated modules:
`bias_controls.py` (`BiasControlEngine`), `provenance.py`, `dataset_split.py`,
`corporate_actions.py`, `adjustments.py`, `signal_validation.py`, `quality.py`,
`reconciliation.py`, `normalization.py`, `calendar.py`, `licensing.py`.

That is an architectural chokepoint plus survivorship/split/restatement handling
and dataset partitioning — categorically stronger than 24 scattered `<= curr_date`
comparisons. SaathiOS additionally has `research_lab/multiple_testing.py` and
`robustness.py`, addressing p-hacking, which TradingAgents does not consider at all.

## Recommendations for SaathiOS

1. **ADOPT the defensive re-filter idiom.** `_verified_rows` re-applies the cutoff
   even though the loader already did. Cheap, and it converts a silent leak into a
   loud one. Apply it at the boundary of every SaathiOS evidence adapter.
2. **ADOPT the undated-record rule.** Undated news is *excluded in backtest, kept
   in live*. Encode that explicitly in the SaathiOS evidence contract.
3. **ADOPT the exclusive upper bound + timezone-aware conversion** convention and
   test it the way `test_news_lookahead.py` does.
4. **DO NOT adopt fiscal-period filtering.** SaathiOS must filter fundamentals on
   *availability date* (filing/publication timestamp), never period end. Record
   both on the evidence record.
5. **Treat any provider field without a publication timestamp as unusable for
   historical analysis.** That rule alone would have blocked Defect 2.
6. **Keep the chokepoint.** Route every new LLM-analyst data source through
   `BiasControlEngine`; do not let an adapter fetch directly.
7. **ADOPT the test style.** `test_news_lookahead.py`, `test_date_boundaries.py`,
   and `test_yfinance_stale_ohlcv_guard.py` are small, sharp, and assert on
   boundary conditions. SaathiOS should have an equivalent per evidence adapter.
