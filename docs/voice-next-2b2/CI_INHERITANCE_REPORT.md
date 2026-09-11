# CI_INHERITANCE_REPORT

## Inherited failure

```text
tests/test_m17_1_live.py::test_live_browser_dom_and_click
AssertionError: assert 'Pilot' in ''
```

PR #28 full-suite: 7299 passed, 1 failed.

## Independent reproduction (this host)

| Run | Result |
| --- | --- |
| 1 | PASS — title `Saathi Pilot Test Site` |
| 2 | PASS |
| 3 | PASS |
| 4 | PASS |
| 5 | PASS |

Browser: Brave on macOS; `LiveBrowserDriver.launch(file://…index.html)`.

## Classification

```text
ENVIRONMENTAL_BROWSER_FAILURE
```

with secondary **TEST_FLAKE** characteristics on Linux CI (empty `title()` race / headless timing).

**Not** `DETERMINISTIC_PRODUCT_FAILURE` from the voice stack.

Evidence: HTML title is correct; failure mode is empty title string on CI only.

## Action

- Did **not** delete or weaken the test.
- Did **not** combine broad browser refactor.
- Classification for certification:

```text
UPSTREAM_CI_FLAKE_PROVEN_AND_DOCUMENTED
```

Bounded repair (e.g. wait-for-title) deferred to a separate non-voice commit if desired.

