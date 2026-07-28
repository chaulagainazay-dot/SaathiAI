# M63 — Navigation

Navigation is data-driven and separated into **Platform**, **Applications**, and
**Administration**. Only the Applications group is derived from module registrations.

## Composition

`saathi-os/lib/modules/shell.js::getShellNavigation(registry)` returns:

```js
{
  platform:      NAV_GROUPS,          // Operate / Work / Business / System (navigation.js, unchanged)
  applications:  { id: "applications", label: "Applications", items: [...] },  // from registry
  administration: ADMIN_GROUP,        // Settings / Identity / Organizations / Permissions / Health / Diagnostics
  groups:        [...platform, applications, administration],
}
```

## Structure

```
Platform
  Operate    Home · Command Center · Missions · Agents · Automation
  Work       Projects · Knowledge · Studio
  Business   Business · Trading Guardian
  System     Monitoring · Security

Applications                (data-driven from ModuleRegistry)
  Trading      /trading      (enabled)
  IELTSAlert   /ielts        (soon)
  HCG POS      /pos          (soon)
  Travel       /travel       (soon)
  Finance      /finance      (soon)

Administration
  Settings · Identity · Organizations · Permissions · Health · Diagnostics
```

## Why platform groups are untouched

`saathi-os/lib/navigation.test.js` locks `NAV_GROUPS` to exactly 4 groups / 12 primary areas. M63
does **not** mutate that model; it composes the Applications and Administration groups alongside it.
This keeps every existing navigation regression green while making application navigation
fully data-driven.

## Adding an application to navigation

Register a `ModuleDescriptor` with `nav_items`. It appears in the Applications group automatically.
Enabled modules link to their first route; placeholders render with a `soon` badge and are not
linked. No shell edits required.

## Backend parity

`GET /api/v1/platform/navigation` returns the same Applications group server-side (requires
`PLATFORM_READ`), so non-shell clients get identical, authoritative navigation data.
