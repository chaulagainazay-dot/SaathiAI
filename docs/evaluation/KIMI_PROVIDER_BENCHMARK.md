# Kimi Provider Benchmark

Status: governed adapter contract integrated; live benchmark deferred.

No `KIMI_API_KEY` was available or requested, and no Moonshot request was
made. Consequently task-success, latency, test-pass rate, context retention,
and tool-discipline values for Kimi are **unknown**, not zero and not
estimated.

| Provider | Task success | Cost | Tool discipline | Decision |
|---|---:|---:|---:|---|
| Ollama / Qwen2.5 1.5B | 5/6 local contracts | $0 marginal API cost | one unsafe memory-write decision | keep default |
| Kimi K2.7 Code | not measured | official $0.95/M cache-miss input, $4/M output | not measured | adapter-contract only |
| Kimi K3 | not measured | official $3/M cache-miss input, $15/M output | not measured | expensive; approval required |

The adapter uses the existing inference/provider boundary, exact HTTPS host
validation, environment-only credential reference, explicit timeout, at most
two retries through provider policy, cancellation-compatible async calls,
token bounds, safe error normalization, no raw prompt audit logging, and
existing circuit-breaker/governance facilities. The priority policy adds:

```yaml
monthly_budget_usd: 20
warning_threshold_usd: 15
hard_stop_usd: 19
emergency_reserve_usd: 1
max_parallel_cloud_agents: 1
max_retries: 2
max_tool_iterations: 20
expensive_model_requires_approval: true
```

Model classes are `local_routine`, `low_cost_cloud`, `coding_primary`,
`multimodal`, and `critical_expensive`. They translate to existing
`ModelRouter` constraints; they do not form a second router. Kimi remains
policy-disabled by default. The Mission Control read model exposes selected
model, routing reason, estimated/actual tokens and cost, cumulative cost,
approval state, and rollback availability.

Live comparison tasks—architecture comprehension, TDD repair, dependency
tracing, mission planning, and optional screenshot analysis—remain deferred
until the user explicitly supplies a credential reference and approves
external data transfer/cost. Evidence:
`artifacts/evaluation/provider-comparison.json`.
