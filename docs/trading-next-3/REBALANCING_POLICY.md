# REBALANCING_POLICY

Generate proposed BUY / SELL / HOLD / NO_ACTION from current → target.

Each row: security, action, current/target weight, weight change, estimated quantity, reference price, estimated notional, reason codes.

- No order submission
- No broker-specific instructions
- Quantity requires non-stale qualified mark
- Net buys must fit available cash after buffer + free cash from sells

