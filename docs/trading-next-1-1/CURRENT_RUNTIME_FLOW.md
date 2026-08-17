# CURRENT_RUNTIME_FLOW — T-NEXT-1.1

## Before cutover

```text
proposal → TG → approval → paper order → fill
  → OMS persist (cash/avg-cost positions)  ← books dual authority
  → UI/risk read OMS state
```

## After cutover

```text
proposal → TG → approval → paper order → fill
  → OMS persist (order lifecycle + reservation shadows)
  → post_accepted_fill → PortfolioLedgerService (CANONICAL)
  → get_account / list_positions / command_center_snapshot read LEDGER
  → TG portfolio inputs from ledger cash/positions (reservations OMS)
```

## Field classification

| Field | Class |
| --- | --- |
| cash (books) | CANONICAL_LEDGER |
| positions / lots / P&L / NAV / exposure | CANONICAL_LEDGER |
| reserved_cash / reserved_quantity | OMS_LIFECYCLE_ONLY |
| OMS avg_cost / oms current_cash shadow | LEGACY_COMPATIBILITY / NOT books |
| order/fill/intent rows | OMS_LIFECYCLE_ONLY |
| Command investment metrics | DERIVED from ledger |

