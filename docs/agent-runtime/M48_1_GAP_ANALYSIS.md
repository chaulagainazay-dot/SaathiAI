# M48.1 — Gap Analysis

| Gap | Severity | Evidence | Recommended milestone |
|---|---|---|---|
| Multiple runtimes (M8 chat, M10, IELTS, pipeline) | HIGH | inventory | M48.2 adapter consolidation docs + single entry facade |
| Contracts not yet wired into Orchestrator.create_run | MEDIUM | new contracts module | M48.2 pre-create validation hook |
| Model router not fully unified with chat helper chains | MEDIUM | model_router vs _llm_helper | M48.2 |
| Live stream cancel under credentials | LOW | M47 limitations | later UX |
| Branch protection not inspectable (private free) | LOW | GH 403 | ops |
| Parallel mission/pipeline vs M10 graph | MEDIUM | graph package | document layering only unless conflict |
| False success risks residual | MEDIUM mitigated | contracts + existing tests | keep fail-closed |
| Secret fixture strings in tests | LOW | m39 test ghp_ dummy | keep tests; scanner allowlist |

## Critical gaps for M48.1

```text
none blocking after contracts slice
```

## Safe next slice (M48.2)

Wire `validate_run_request` at Orchestrator.create_run entry; emit contract violations as BLOCKED with evidence; optional single façade `start_agent_run()`.
