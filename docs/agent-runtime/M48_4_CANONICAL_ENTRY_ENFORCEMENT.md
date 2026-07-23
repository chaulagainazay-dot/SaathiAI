# M48.4 — Canonical Entry Enforcement

- Production paths: API, CLI, chat orchestration, M8 run_agent → `start_agent_run`
- `skip_contract=True` requires `PYTEST_CURRENT_TEST` env (pytest only)
- Negative test: skip_contract blocked outside pytest
