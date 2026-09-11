# BROWSER_FAILURE_CLASSIFICATION

## Classification

```text
DOM_READINESS_RACE
```

## Evidence

- `LiveBrowserDriver.launch` waited only for CDP `/json` websocket availability, not `document.readyState`.
- Local Mac: 5/5 passes after fix; pre-fix sometimes green (timing-dependent).
- CI Linux: slower file:// load → title may resolve while `#submit` query still races or CDP evaluate returns empty.

## Fix

- `wait_dom_ready(timeout=5.0)` after CDP connect and after `navigate`.
- `wait_for_selector(selector, timeout=5.0)` bounded poll.
- Test asserts bounded readiness before DOM assertions.
- No unbounded retry; no skip-on-CI; no fixed `sleep(5)`.
