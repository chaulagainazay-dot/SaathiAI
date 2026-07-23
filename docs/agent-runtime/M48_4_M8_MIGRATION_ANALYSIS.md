# M48.4 — M8 Migration Analysis

## Disposition

```text
WRAP_CANONICAL_RUNTIME
```

## Callers
- `ChatEngine.run_agent` / `delegate`
- `chat/api.py` run_agent route

## Behavior
- Role prompts in AGENT_ROLES; chat agent_run table; gateway chat send historically
- M48.4: validates via start_agent_run, force_agent DAG, lifecycle lease, chat row compatibility

## Mapping
coder→builder; capabilities plan/research/code/review/architect/write/ceo_brief
