**Production authorized: false.** Local-only private alpha.

# Private Alpha Automations

## Defaults

- Global `automation_execution_enabled`: **false**
- Per-automation `enabled`: **false** until explicit enable after validation

## Authority path

```
MissionRuntime → PlanValidator → ExecutionGateway → ApprovalCenter → Evidence/Audit
```

No second scheduler. No self-approval. No arbitrary shell. No gateway bypass.

## States

`DRAFT` `VALIDATED` `ENABLED` `PAUSED` `RUNNING` `SUCCEEDED` `FAILED`
`BLOCKED_APPROVAL` `BLOCKED_POLICY` `CANCELLED` `DISABLED`

## Allowed private-alpha actions (read/notify/low-risk)

- hcg_daily_summary
- ielts_daily_progress
- weekly_report
- create_local_backup
- notify_low_inventory
- notify_missed_ielts_task
- notify_unresolved_approval
- notify_app_health

## Forbidden

Withdraw funds, trade, paid providers, permission changes, self-approve, deploy,
public network exposure, production mutation, Trading Guardian bypass,
cross-tenant mutation, arbitrary shell.

## Controls

- PlanValidator structural gate
- Approval Center when policy requires
- Idempotency keys
- Max retries = 2
- Overlap prevention (one RUNNING per automation)
- Cancellation supported
- Evidence + audit + notifications on success
