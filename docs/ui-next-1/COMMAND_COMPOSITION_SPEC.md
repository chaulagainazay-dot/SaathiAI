# COMMAND_COMPOSITION_SPEC

## Layout regions (implemented)

1. **Authority strip** — environment, execution, trading, TG, live orders, providers, model, voice, system  
2. **Command composer** — Ask Saathi / mission / chat / voice settings (no new voice runtime)  
3. **Current activity** — missions + agents (stage-based progress)  
4. **Attention queue** — aggregated priorities  
5. **Investment snapshot** — paper-only; NOT AVAILABLE for missing metrics  
6. **System state** — subsystem health vocabulary  
7. **Evidence / activity timeline** — provenance-honest  

## Data flow

```
useCommandCenter
  → settled multi-fetch (partial OK)
  → aggregateAttention
  → composeCommandCenterViewModel
  → presentational components
```

No component submits tools or orders. Approvals remain on `/approvals`.
