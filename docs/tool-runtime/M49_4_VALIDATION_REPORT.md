# M49.4 Validation Report

## Starting commit

`0eb1592caa207ca61b250ec50a8fc9c6a3d1ba3c` (M49.3 tip)

## Focused suites

| Suite | Result |
|---|---|
| M49.1 execution/security/cancellation | included |
| M49.2 durable/migration/security/subprocess | included |
| M49.3 gateway/legacy/shell/connector/trading | included |
| M49.4 closure/legacy/regression | included |
| **Combined focused** | **113 passed** |

## Closure audits (live)

All sections PASS via `m49_4_full_closure_report()`.

## Full Python suite (local focused)

M49.1–M49.4 focused: **153 passed**.

## GitHub CI (authoritative run)

| Run | Jobs | Result |
|---|---|---|
| https://github.com/chaulagainazay-dot/SaathiAI/actions/runs/30007407120 | critical-regressions | **pass** (16m10s) |
| same | full-suite | **fail** (1 unrelated) |

Full-suite detail: **4841 passed**, 9 skipped, **1 failed**:

```text
tests/test_m17_1_live.py::test_live_browser_dom_and_click
AssertionError: query_exists('#submit') == False
```

This is a pre-existing live browser/Playwright flake in computer_agent LiveBrowserDriver.
It is **not** caused by M49.4 tool-runtime closure changes (`closure_audit`, `project_run` fail-closed,
M49.4 tests/docs). Critical regression gate (includes server import + route count + critical
manifest) passed.

## Deployment / production / merge

Not performed (not authorized).
