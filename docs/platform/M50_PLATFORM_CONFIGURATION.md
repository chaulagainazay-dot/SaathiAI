# M50 Platform Configuration

Stored keys under `platform_config`:

- models
- connectors (forced `mutations=DRY_RUN_ONLY`, `live=false`)
- runtime
- notifications
- privacy
- security (session/approval TTL)
- trading_guardian (forced `ADVISORY_ONLY`)

Updates that attempt live connectors or non-advisory trading are **blocked**.

## State

Configuration active with production-safe defaults.
