# M64 — Test Results

Environment: macOS, Python 3.12.13 virtualenv, Node 26.4.0, Next.js 15.5.20,
checkout-local loopback backend and production frontend.

## Backend targeted and regression gates

Command:

```text
pytest -q tests/test_m64_module_discovery.py tests/test_m64_module_api.py
tests/test_m64_localhost_binding.py tests/test_m63_module_registry.py
tests/test_m50_api.py tests/test_m36_authorization_and_security.py
tests/test_m62_8_workspace.py tests/test_execution_gateway.py
tests/test_agent_runtime.py tests/test_m52_platform_agent_runtime.py
tests/test_m50_approval_and_runtime.py
```

Result: **176 passed, 0 failed, 18 warnings in 4.40s**.

This covers authenticated discovery, API 401/404/contract behavior, `PLATFORM_READ`,
RBAC, tenant/workspace isolation, localhost default, M63 registry compatibility,
Trading M62.8 workspace behavior, ExecutionGateway, PlatformAgentRuntime, and
approval/runtime regressions.

Full backend suite (run after the final backend implementation changes and before
frontend-only completion work): **5221 passed, 1 skipped, 0 failed, 319 warnings in
812.26s (13m32s)**. Backend implementation did not change afterward, so the result
remains valid. See `FULL_SUITE.txt`.

## Frontend

```text
npm test
175 passed, 0 failed, 0 skipped (29 M64 discovery/shell tests)
final rerun duration: 213.05ms

npm run lint
clean

configured standalone typecheck
none (JavaScript project; Next build performs its configured validity checks)

npm run build
Next.js 15.5.20 production build compiled successfully
69 static/dynamic pages generated; /apps and /trading included
```

## Browser certificate

```text
npm run cert:m64
PASS: 20 hard gates, 12 state gates, 6 responsive gates,
3 focused accessibility gates
```

Certified:

- unauthenticated/authenticated shell transitions and authenticated module request;
- production Sidebar and CommandPalette use backend Applications data;
- Trading actionable/opening with paper-only framing;
- four placeholders non-actionable and direct placeholder route truthful;
- safe unknown route;
- context switch clears old actionable state before refetch;
- session-expired, permission-restricted, malformed, offline, and bounded-retry states;
- real Logout clears token and Applications state;
- desktop/tablet/mobile layout and horizontal-overflow checks;
- visible keyboard focus, semantic controls, and textual statuses;
- zero page errors, unexpected console errors, or framework overlays.

Known unrelated browser limitation: the global TopBar approvals request produces a
CORS plus failed-resource pair on each viewport (six expected messages total). It
does not involve module discovery and is recorded separately in
`M64_BROWSER_CERT.json`.

Safe evidence:

- `M64_BROWSER_CERT.json`
- `m64_apps_desktop.png`
- `m64_apps_tablet.png`
- `m64_apps_mobile.png`
- `m64_placeholder_guard.png`

## Hygiene

`git diff --check` and `git diff --cached --check` were clean before final staging.
