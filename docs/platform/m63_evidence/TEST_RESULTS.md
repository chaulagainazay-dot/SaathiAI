# M63 — Test Results

Environment: macOS (Darwin 25.5.0), Python 3.12.13 `.venv`, Next.js 15.1.6, single host, localhost.

## Backend

```
python -m pytest tests/test_m63_module_registry.py -q
16 passed
```

Coverage: registration, duplicate rejection, missing-field rejection, enable/disable + lists,
data-driven navigation, dashboard cards (one per module), widget/search/workspace composition,
permission-namespace directory, health report, default registry (Trading enabled + 4 placeholders),
Trading declares no live capability, serializable shape, singleton stability, and
registration-grants-no-capability (RBAC authoritative).

Regression around the api.py addition:
```
python -m pytest tests/test_m62_8_workspace.py tests/test_m62_5_paper_broker.py \
  tests/test_m62_7_safety.py tests/test_m62_2_market_data.py tests/test_m63_module_registry.py -q
123 passed
python -m pytest tests/test_m50_api.py -q
2 passed        # platform router mounts; existing endpoints unaffected
```

Full suite: see FULL_SUITE.txt in this directory.

## Frontend

```
saathi-os $ npm test
146 pass, 0 fail   (130 prior + 16 new module/shell tests)

saathi-os $ npm run lint
clean (eslint . --max-warnings 5)

saathi-os $ npm run build
success — /apps route built (4.54 kB), all /trading routes intact
```

## Registry snapshot

`MODULE_REGISTRY_SNAPSHOT.json` — installed: 5, enabled: 1 (trading), dashboard cards: 5,
search providers: 5. Trading health = healthy; placeholders health = not_implemented.
