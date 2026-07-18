# M36 — Validation

## Focused offline suites

- `tests/test_m36_authorization_and_security.py`
- `tests/test_m36_real_session_lifecycle.py`
- `tests/test_m36_transport_and_scope.py`
- `tests/test_m36_certification_and_evidence.py`

## Sequence

1. Focused M36 tests
2. M31 regression
3. M32–M35 regressions
4. Leak scan on evidence
5. Critical / release / runtime gates as available
6. `git diff --check`
7. Full suite: `.venv/bin/python -m pytest -q --tb=line`

## Live gate (all required)

Audit complete · offline tests green · leak scan clean · CLI rejects raw secrets ·
authorization · qualified account · secret reference validated · scope policy ·
capability intersection · call budget · cleanup plan · runtime acks · live flag.
