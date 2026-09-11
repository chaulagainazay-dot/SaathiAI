# Adapter contract

Adapt the existing `MarketDataProvider` interface and return canonical MD-1 objects only. Provider dictionaries must not reach risk, construction, guardian, ledger, or UI authority paths. Optional depth/trades remain absent until a licensed source proves support. The adapter is read-only and has no account or execution methods.
