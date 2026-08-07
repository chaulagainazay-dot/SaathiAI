# M48.3 — State Transition Matrix

Preserved M10 RunState vocabulary. M48.3 adds TIMED_OUT from pre-execution and waiting states (QUEUED, PAUSED, AWAITING_APPROVAL, etc.).

Invalid (enforced):
- any terminal → RUNNING
- SUCCEEDED/COMPLETED → non-terminal
- CANCELLED → RUNNING

See `models._TRANSITIONS` for full matrix; tests in test_agent_runtime + test_m48_3.
