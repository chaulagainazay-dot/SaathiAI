# M59 — Production-Build Browser Certification (Workstream 8)

Harness: `saathi-os/scripts/m59_browser_cert.mjs`
(`npm run cert:m59:build` — production; `npm run cert:m59` — dev regression).

The harness boots an **isolated** SQLite BFF (127.0.0.1 only), seeds real fixtures,
runs `next build` + `next start`, and drives headless Chromium. Exit 0 only when
every hard gate passes.

## Fixtures (test-only, isolated)

Owner + org + workspace; one agent binding; one execution; one project; one active
mission; one high-risk (DESTRUCTIVE) **pending** approval (decision surface); one
**rejected** approval (settled-state fixture). All in a throwaway `platform.db`
under `$TMPDIR`, never production data.

## Result — verdict PASS (mode=build)

All hard gates green:

```
production_build_succeeds     prod_server_starts
route_platform  route_ops
route_missions  route_mission_detail
route_agents    route_agent_detail
route_approvals route_approval_detail   approval_decision_surface
route_attention route_attention_detail
context_drawer_opens          command_palette_opens
real_api_binding              reduced_motion            responsive_mobile
accessibility_no_critical     no_page_errors            no_hydration_errors
```

Soft gates green: `context_drawer_escape_closes`, `command_palette_escape_closes`.

- **No page errors, no hydration errors** on any M59 route (shell hydration
  baseline = 0, attributed separately from a non-M59 control page).
- **Real API binding** confirmed: the seeded mission, agent binding, and approval
  render in their respective workspaces from live server data.
- **Approval decision surface** present on the pending high-risk approval
  (Approve + Reject controls).
- **Localhost-only** binding retained; **production remains unauthorized**;
  connectors dry-run; financial + trading execution disabled.

## Development regression — verdict PASS (mode=dev)

`npm run cert:m59` re-runs the same harness against `next dev` and also reaches
verdict PASS. (Dev uses on-demand route compilation; under heavy concurrent load
the first hit to an uncompiled route can occasionally exceed the wait window — the
production build precompiles all routes and is the authoritative gate.)

Evidence: `docs/platform/m59_evidence/m59_browser_cert.json` + 15 screenshots.
