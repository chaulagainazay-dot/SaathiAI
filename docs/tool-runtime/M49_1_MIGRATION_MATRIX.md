# M49.1 Migration Matrix

| tool_id | class | decision | proof |
|---|---|---|---|
| m49.echo_readonly | READ_ONLY / NO_SIDE_EFFECT | MIGRATE_NOW | tests execution |
| m49.local_note_write | LOCAL_MUTATION / LOCAL_REVERSIBLE | MIGRATE_NOW | approval+idempotency tests |
| m49.timeout_demo | TIMEOUT_ONLY | MIGRATE_NOW | cancellation tests |
| m49.cooperative_cancel | COOPERATIVE | MIGRATE_NOW | cancel tests |
| m49.financial_execution_stub | PROHIBITED | BLOCK_UNSAFE | security tests |
| saathi.tools.* | LEGACY | DEFER | inventory |
| connector tools | LEGACY | DEFER | inventory |
| trade.execute | FINANCIAL | PROHIBITED | trading boundary |
