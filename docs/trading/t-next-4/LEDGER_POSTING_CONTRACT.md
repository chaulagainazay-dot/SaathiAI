# Canonical Ledger Posting Contract

## Separation

The OMS does **not** mutate positions. The flow is:

```
execution report → validated fill → post_accepted_fill → PortfolioLedgerService
                                                          → cash / lots / positions / NAV
```

`saathi/platform/fund_ledger/` owns accounting. `paper_trading/` owns order
lifecycle. Neither reaches into the other's state.

## Every mutation carries provenance

`FillPostingStore.record_attempt` writes `fill_id`, `fund_id`, `account_id`,
`order_id`, `status`, `idempotency_key` (`fill:{fill_id}`), `payload`, and
`ledger_event_id`. The ledger itself is **event-sourced**:
`PortfolioLedgerService._append` writes typed events, and `replay(fund_id)` and
`snapshot(fund_id)` rebuild state from them. Nothing is mutated in place.

## Idempotency

`post_accepted_fill` short-circuits before doing any work:

```python
prior = posts.get_post(fill_id)
if prior and prior.get("status") in (POST_POSTED, POST_DUPLICATE) and prior.get("ledger_event_id"):
    return {..., "idempotent": True}
```

A second posting of the same `fill_id` returns the original `ledger_event_id`
and moves nothing.

## Failure never erases a fill

The posting function catches every exception rather than unwinding the OMS fill:

```python
except Exception as e:  # noqa: BLE001 — must not unwind OMS fill
    posts.record_attempt(..., status=POST_FAILED, error=str(e), ...)
    return {"status": POST_FAILED, ..., "portfolio_status": "RECONCILIATION_REQUIRED"}
```

This is the right trade. A fill that happened at the venue is a fact; failing to
post it must not delete the fact. The attempt is recorded as `FAILED`, the caller
is told `RECONCILIATION_REQUIRED`, and `retry_pending_posts` can drain the
backlog once the ledger is healthy. Verified by `F10`.

## Proven properties

| Property | Mechanism | Test |
|---|---|---|
| Duplicate fill cannot double cash or position | `fill_id` short-circuit + ledger event dedup | `F6` |
| Cancelled order with no fill cannot change the ledger | posting is driven by fills only; no fill, no posting | `F8`, structural |
| Rejected order cannot change the ledger | a rejected order never produces a fill | structural + state machine `F9` |
| Unknown state cannot silently change the ledger | posting failure returns `RECONCILIATION_REQUIRED`, never a silent success | `F10` |
| Ledger drift is detectable | `ReconciliationAuthority` compares ledger cash and positions against expectations | `F11` |

## What the ledger does not have

No withdrawal authority. `record_withdrawal_sim` is explicitly a simulation and
is named as such; `test_no_withdrawal_authority_in_execution_plane` asserts no
real withdrawal, transfer-out, or payout function exists in the execution plane.
