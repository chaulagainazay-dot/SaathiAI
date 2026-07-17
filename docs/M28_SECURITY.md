# M28 Security

## Preserved invariants

```text
production_certified = computed
cloud fallback = disabled
direct provider bypasses = 0
connector bypasses = 0 (production scan)
process-local production authorities = 0
residual inference exceptions = 0
Trading Guardian = UNCHANGED / UNENGAGED
```

## M28 additions

* Side-effect fail-closed for FINANCIAL / ACCOUNT_CHANGE / PROHIBITED  
* No caller override of adapter, rollout, approval, or side-effect class  
* No substrate-only connector execution when gateway missing  
* Live manager adapters blocked without governed ACTIVE path  
* Bypass guard AST scan with explicit allowlist  
* Secrets still forbidden in payloads/headers; evidence redacted  

## Trading Guardian

Not modified. Trading connectors cannot register. Trading operations denied at side-effect classification.
