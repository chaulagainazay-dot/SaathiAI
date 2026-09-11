# Browser Test Inventory

## Files referencing a browser stack (9)

`test_connector_drivers.py` · `test_m17_26_production_browser.py` ·
`test_fm_i1_agent_harness.py` · `test_failure_injection.py` ·
`test_m17_24_browser_dispatch_governance.py` · `test_browser_service.py` ·
`test_infra_diagnostics.py` · `test_m17_1_live.py` · `test_infra_events.py`

Additional `*live*` / `*browser*` named files: `test_browser_session.py`,
`test_human_browser.py`, `test_m15_1_live_local.py`, `test_m17_23_browser_execution_gateway.py`,
`test_m17_25_interactive_browser.py`, `test_m17_9_live.py`,
`test_m20_6_live_local_certification.py`, `test_m25_live_provider_certification.py`,
`test_m34_live_external_runtime.py`, `test_m34_live_external_security.py`,
`test_m39_live_validation.py`, `test_m40_live_certification.py`,
`test_m17_11_notification_delivery.py`.

## Existing guard pattern

Browser tests already use a `skip_no_browser` decorator and skip cleanly when no
browser is present. That is why the unfiltered suite completes on this host — the
browser tests are not running here, they are skipping.

## Did a browser cause the hang?

**No.** Ruled out on evidence:

- the stalled interpreter had no browser child process;
- the minimal two-test reproduction contains no browser code at all;
- the deadlock stack is entirely SQLite DDL inside `SecurityStore.__init__`.

No test was found that launches a browser without closing it, waits on an
unavailable server, or spawns a server that never terminates.

## Markers applied

| File | Marker |
|---|---|
| `tests/test_m17_1_live.py` | `@pytest.mark.browser` on 4 live-browser tests |
| `tests/test_m17_9_live.py` | module-level `pytest.mark.browser` |

These make the boundary explicit instead of relying on a self-skip that silently
changes behaviour depending on what happens to be installed.

## Separability

Browser certification is separable from the canonical offline suite:

```bash
pytest tests -m "not browser and not live and not external and not network"   # offline
pytest tests -m browser                                                        # browser only
```

`saathi-os` JavaScript/browser certification is a separate npm toolchain and is
out of scope for the Python offline suite.
