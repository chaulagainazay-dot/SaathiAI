# M48.4 — Compatibility Bridge

`ChatEngine.run_agent` → `start_agent_run(strategy=single, force_agent=…, execute=True)` with injected `llm_fn`.

Legacy response: `{status, message, canonical_run_id, canonical_state, …chat agent_run fields}`.

Unsupported: streaming deltas on single-agent (documented LIMITATION); full team streaming via start_orchestration only.
