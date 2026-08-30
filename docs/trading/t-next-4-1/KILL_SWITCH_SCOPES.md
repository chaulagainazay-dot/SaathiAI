# Kill-Switch Scopes

`BLOCK_NEW_ORDERS` denies submit and retry while allowing reconciliation, fill
ingestion, and ledger posting. A broader `BLOCK_ALL_EXECUTION_ACTIONS` may deny
new submit/retry/cancel actions, but must still permit authoritative fill
recording and reconciliation. Existing safety breakers remain authoritative.
