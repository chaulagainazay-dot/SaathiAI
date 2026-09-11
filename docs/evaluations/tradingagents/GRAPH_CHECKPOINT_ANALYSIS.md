# Graph, Routing, Checkpoint and Recovery

## LangGraph usage

`graph/setup.py` builds a `StateGraph` over `AgentState` (a `TypedDict` in
`agents/utils/agent_states.py`). Nodes: 4 analysts × (agent, tool, clear) triples,
Bull, Bear, Research Manager, Trader, 3 risk debators, Portfolio Manager.

Edges are almost entirely **static and linear**. Only three conditional edges exist:

1. per-analyst `should_continue_*` — "did the model emit tool calls? loop : advance"
2. `should_continue_debate` — count-based alternation
3. `should_continue_risk_analysis` — count-based three-way rotation

### Routing logic in full

```python
def should_continue_debate(self, state) -> str:
    if state["investment_debate_state"]["count"] >= 2 * self.max_debate_rounds:
        return "Research Manager"
    if state["investment_debate_state"]["current_response"].startswith("Bull"):
        return "Bear Researcher"
    return "Bull Researcher"
```

Turn-taking is decided by **string-prefix matching on the previous message**
(`startswith("Bull")`). Termination is a turn counter. There is no convergence
detection, no "has new evidence appeared" test, no deadlock or repetition guard,
and no early exit when both sides already agree.

### Assessment

The graph is a fixed pipeline with two bounded loops. Nothing here requires a
graph engine. LangGraph provides: typed shared state, checkpointing, and the
`tools` loop convention. Of those, only checkpointing is non-trivial to rebuild.

**SaathiOS already has** `research_orchestrator/` (`scheduler.py`, `queue.py`,
`workers.py`, `dependencies.py`, `sessions.py`, `budget.py`, `estimator.py`,
`templates.py`, `journal.py`, `certification.py`) plus the AgentHarness and mission
framework. That is a superset of what this graph does, with budget control and
certification that LangGraph has no notion of.

### Verdict on LangGraph runtime

**DEFER (do not add).** Reasons, in order of weight:

1. **No capability gain.** The realised topology is linear + two counters.
   SaathiOS's orchestrator expresses that today.
2. **Authority risk.** A second orchestration runtime creates a second place where
   execution order and state transitions are defined — exactly the duplicate-machinery
   failure `AGENTS.md` forbids.
3. **Dependency burden.** `langgraph` + `langchain-core` + provider integrations +
   `langgraph-checkpoint-sqlite` measured at **~288 MB installed** in the isolated
   venv, on an 8 GB host.
4. **Debuggability.** Graph-engine stack traces are worse than a plain scheduler's
   for a pipeline this simple.

**ADAPT the patterns instead:** typed shared state object, explicit node contracts,
bounded loop counters as first-class config, and a deterministic "clear messages"
step between stages to stop context accumulation.

## Checkpointing

`graph/checkpointer.py` (98 lines), backed by `langgraph.checkpoint.sqlite.SqliteSaver`,
one SQLite DB per ticker under `<data_dir>/checkpoints/<TICKER>.db`.

```python
def thread_id(ticker: str, date: str, signature: str = "") -> str:
    base = f"{ticker.upper()}:{date}"
    if signature:
        base = f"{base}:{signature}"
    return hashlib.sha256(base.encode()).hexdigest()[:16]
```

| Property | Implementation | Assessment |
|---|---|---|
| Storage | SQLite per ticker | Fine |
| Resume identity | `sha256(ticker:date:signature)[:16]` | **Good** |
| **Graph-shape versioning** | `signature` folds in run choices that change graph shape, so a resume under a different graph cannot reuse an incompatible checkpoint (#1089) | **Excellent — the best idea in this module** |
| Path safety | `safe_ticker_component(ticker)` rejects traversal before building the DB path | **Good** |
| Explicit cleanup | `clear_checkpoint`, `clear_all_checkpoints` | Adequate |
| Stale-checkpoint expiry | none (no age policy) | **Gap** |
| Partial-failure semantics | inherited from LangGraph; not independently specified | **Gap** |
| Corruption handling | `sqlite3.OperationalError` swallowed on delete | Weak |

## Verdicts

| Item | Verdict | Rationale |
|---|---|---|
| LangGraph runtime | **DEFER** | No capability gain; duplicate orchestration; 288 MB; 8 GB host |
| Graph/state patterns (typed state, node contracts, bounded counters, message-clear step) | **ADAPT** | Cheap, useful, no dependency |
| Checkpoint **shape signature** in the resume key | **ADAPT — high value** | Directly applicable to `research_orchestrator/sessions.py`; prevents resuming a session under a changed pipeline |
| Path-safe identifier component before filesystem use | **ADAPT** | Small, correct, defends a real attack |
| SQLite checkpoint store itself | **REJECT DUPLICATE** | `research_orchestrator/storage.py` + `sessions.py` already own this |
| Stale-checkpoint expiry | **ADAPT (as improvement to SaathiOS)** | Neither system has it; SaathiOS should |
