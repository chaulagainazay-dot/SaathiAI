# PAPER_FILL_INGESTION

```text
Agent proposal → TG → Approval → Paper OMS → accepted PaperFill
                                              ↓
                               post_paper_fill_to_ledger / record_fill
```

Agents cannot write positions/cash/NAV. Fill identity = `fill_ref` / idempotency key `fill:{id}`.

