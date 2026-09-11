# Fresh-Context Review Findings — NEPSE-CAL-1.1

A reviewer with no prior context was given the migration diff and the NEPSE
facts (Sunday–Thursday trading, Friday–Saturday closed, `Asia/Kathmandu`
UTC+05:45 no DST) and asked only for concrete defects across seven categories.

Four findings. Three fixed here; one recorded as a limitation.

---

## R-A — the calendar gate could be skipped by omission *(severe, fixed)*

`saathi/platform/strategy/engine.py`

The coverage gate keyed on `calendar_name == "NEPSE"`. `run_backtest` takes
`calendar: str = "DEFAULT_24_5"`. A caller passing a **NEPSE instrument** while
leaving `calendar` at its default therefore skipped the gate entirely —
`NEPSE_CALENDAR_COVERAGE_REQUIRED` was unreachable on that path, and the
backtest would produce fills over dates with no sourced calendar truth.

The research runner is not exposed, because `research.py:272` inherits
`calendar_name` from the dataset manifest. The exposure is any **direct**
`run_backtest` call — which is exactly what the existing test
`test_direct_nepse_backtest_fails_closed_when_calendar_truth_is_uncovered`
exercised, but it passed `calendar="NEPSE"` explicitly, so the omission path was
never covered.

**Fix.** Derive the requirement from instrument identity and refuse the
mismatch:

```python
if str(instrument).upper().startswith("NEPSE:") and calendar_name != "NEPSE":
    return _fail("NEPSE_INSTRUMENT_REQUIRES_NEPSE_CALENDAR", status="REJECTED")
```

Fail-closed: a NEPSE instrument cannot run under a Western calendar by accident
or by explicit mis-declaration. Three regression tests, including one asserting
non-NEPSE instruments are unaffected.

---

## R-C — confirmed-closed bars blocked in one quality engine but not the other *(fixed)*

`saathi/platform/tg/market_data/quality.py`

`tg/historical/quality.py` folds `confirmed_closed_bars` into `critical` and
forces `REJECTED`/`QUARANTINED`. `tg/market_data/quality.py` appended a finding
and nudged the `validity` score but **never populated `blocking`**, so a dataset
carrying NEPSE Friday/Saturday bars could still certify as
`RESEARCH_USABLE_WITH_WARNINGS` or `HIGH_CONFIDENCE`.

Two engines, same dataset, different verdicts.

**Fix.** `blocking.append("confirmed_closed_session_bar")`, **and** the code
added to the escalation list in `_finalize` — without that second half the
defect blocked but only reached `LIMITED_USE`, still disagreeing with the
historical engine. Now both force `QUARANTINED`.

---

## R-D — offset-less timestamps escaped the Kathmandu conversion *(fixed)*

`saathi/platform/tg/market_data/quality.py`

```python
local_day = (parsed.astimezone(NEPAL_TZ).date()
             if parsed.tzinfo is not None and nepse_calendar is not None
             else date.fromisoformat(ts[:10]))
```

A timestamp with no offset fell through to slicing the raw string. At **+05:45**
that is materially wrong: `2026-09-03T19:00:00` is Thursday in UTC but
`2026-09-04T00:45` in Kathmandu — a **Friday**, which NEPSE is closed for. Any
instant in the UTC 18:15–23:59 window lands on the following Nepali day, so a
confirmed-closed bar was silently accepted as a valid Thursday bar.

This is the class of error a non-whole-hour offset produces and a whole-hour one
hides.

**Fix.** Treat a naive timestamp as UTC and always convert; never slice.

---

## R-B — `exchange` is free text and the API defaults it to `XNAS` *(recorded, not fixed)*

`saathi/platform/tg/market_data/quality.py:28` selects the NEPSE calendar with
`exchange == "NEPSE"`, where `exchange` comes from the dataset record.
`saathi/platform/api.py` declares `MdRegisterBody.exchange: str = "XNAS"`,
independent of `market`. A NEPSE dataset registered with `market="NEPSE"` but
`exchange` left at its default falls into the generic branch and is judged by
Western weekend rules.

**Not fixed in this milestone, deliberately.** `saathi/platform/api.py` is
outside the migration's file set, the default has other consumers, and changing
a public API default is a behavioural change that deserves its own analysis
rather than being folded into a calendar migration.

R-A closes the equivalent hole on the backtest path, which is where fills are
produced. The residual exposure is dataset *quality classification* being too
lenient for a mis-registered NEPSE dataset — it does not produce trades.

Recorded in `LIMITATIONS.md`. The fix, when taken, is to cross-check `exchange`
against instrument identity rather than trusting a free-text field.

---

## Categories reported clean

| Category | Verdict |
|---|---|
| Historical import — silent relabelling or session-meaning drift | **NONE.** `DatasetManifest.to_public()` refuses to relabel a pre-migration artifact as canonical when `calendar_version` is empty; `calendar_coverage_status` must equal `COMPLETE` for both `DatasetVersion.promotable` and the research-run gate, so a record missing the new metadata fails closed. |
| Session/staleness for quotes | **NONE.** `classify_quote` resolves NEPSE session truth before the freshness check, returning `MARKET_CLOSED` for confirmed-closed days and `UNVERIFIED` for unknown coverage — never `STALE`, never `VALID`. |
| `NepseCalendar` fail-closed behaviour | **NONE.** No `covered_years` entry ⇒ `UNKNOWN` ⇒ `is_trading_day()` is `False`. |

One forward-looking note the reviewer raised and I am carrying rather than
acting on: `is_bar_fresh()` in `saathi/platform/market_data/quality.py` has no
calendar awareness, so a bar carried over a NEPSE weekend would read as stale on
wall-clock age alone. It is currently unreferenced anywhere in the codebase, so
it is not a live defect — but it is a trap for whoever wires it up. Recorded in
`LIMITATIONS.md`.
