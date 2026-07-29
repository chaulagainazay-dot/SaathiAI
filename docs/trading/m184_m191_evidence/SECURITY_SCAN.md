# M184–M191 Security / authority scans

## Live broker capability

- No live order endpoints added
- Binance adapter: public klines path only; private path markers rejected
- `credentials_required=False` on all historical adapters
- `LIVE_TRADING_AUTHORIZED = False`, `LIVE_ORDER_CAPABLE = False`, `BROKER_CREDENTIAL_SUPPORT = False`

## Fixture authority

- `AUTHORITATIVE_RESULT_REQUIRES_NON_FIXTURE_DATA` retained
- Fixture/synthetic cannot yield `PAPER_ELIGIBLE` (tested)

## LLM boundary

- `llm_may_approve=False`, `llm_may_alter_metrics=False` on scorecards
- Deterministic gates only

## Public bind

- Browser cert binds `127.0.0.1` only

## Look-ahead

- Walk-forward `final_test_untouched` + `selected_before_test` retained from M178

## Corporate-action consistency

- Raw prices immutable; adj_* separate; audit trail recorded
