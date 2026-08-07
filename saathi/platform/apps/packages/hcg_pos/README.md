# HCG Operations

First-party hospital cafeteria operations application for SaathiOS.

Runs through the Universal Application Runtime (`saathi.hcg_pos`).

## Capabilities

Sales/POS, orders, kitchen queue, menu, inventory, purchases, expenses,
customer credit ledger, supplier dues, cashier shifts, cash reconciliation,
dashboard reporting, search, notifications, Yeti grounded Q&A, backup/restore.

## Money

Integer minor units (NPR paisa). No binary floating-point financial math.

## Posture

- Local-first
- Demo/certification synthetic data
- Manual QR recording only (no live payment gateway)
- Production not authorized
- Does not touch live HCG POS

## UI

`/apps/hcg` inside the SaathiOS Unified Shell.
