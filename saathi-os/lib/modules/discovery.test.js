/**
 * M64 — authenticated module discovery + shell authority tests (node:test).
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  normalizeModule,
  classifyError,
  fetchModuleDiscovery,
  isActionable,
  MODULE_STATE,
} from "./client.js";
import { bootReducer, initialBootState, BOOT, canRenderModules } from "./bootstrap.js";
import { detectDrift, driftSummary } from "./drift.js";
import { evaluateModulePath, evaluateModuleRoute, GUARD, moduleForPath } from "./guard.js";
import { safeIcon, FALLBACK_ICON } from "./icons.js";
import {
  applicationCommandsFromBackend,
  applicationsGroupFromBackend,
  getShellNavigationFromBackend,
} from "./shell.js";
import { NAV_GROUPS } from "../navigation.js";

function backendModule(over = {}) {
  return {
    id: "trading", name: "Trading", version: "62.9", state: "available",
    category: "trading", description: "d", icon: "◈", status: "enabled",
    enabled: true, implemented: true, health: "healthy",
    routes: ["/trading"], capabilities: ["paper_trading"], feature_flags: { live_trading: false },
    permissions: ["paper_account"], nav_items: [{ id: "t", label: "Overview", href: "/trading" }],
    dashboard_widgets: [], ...over,
  };
}

// ── client: normalize + validate ────────────────────────────────────────────
describe("module client", () => {
  it("normalizes a valid descriptor and derives actionable from backend state", () => {
    const m = normalizeModule(backendModule());
    assert.equal(m.id, "trading");
    assert.equal(m.state, "available");
    assert.equal(m.actionable, true);
    assert.equal(isActionable(m), true);
  });

  it("non-available backend state is never actionable", () => {
    for (const st of ["degraded", "unavailable", "disabled", "not_implemented", "permission_restricted"]) {
      const m = normalizeModule(backendModule({ state: st }));
      assert.equal(m.actionable, false, st);
      assert.equal(isActionable(m), false, st);
    }
  });

  it("rejects malformed descriptors (fail closed)", () => {
    assert.throws(() => normalizeModule(null));
    assert.throws(() => normalizeModule({ id: "x" })); // missing name/version/state
  });

  it("classifies errors by status/category", () => {
    assert.equal(classifyError({ status: 401 }), "session_expired");
    assert.equal(classifyError({ status: 403 }), "permission_restricted");
    assert.equal(classifyError({ status: 404 }), "not_found");
    assert.equal(classifyError({ status: 500 }), "server_error");
    assert.equal(classifyError(new Error("Failed to fetch")), "network");
  });

  it("fetchModuleDiscovery requires a token (fail closed)", async () => {
    await assert.rejects(() => fetchModuleDiscovery({ token: "" }), /authentication required/);
  });

  it("fetchModuleDiscovery normalizes and drops malformed modules", async () => {
    const platFn = async () => ({
      contract_version: "m64.1",
      installed: [backendModule(), { id: "bad" /* missing fields */ }],
      navigation: { group: "applications", modules: [] },
      dashboard_cards: [],
    });
    const disc = await fetchModuleDiscovery({ token: "t", platFn });
    assert.equal(disc.modules.length, 1);
    assert.equal(disc.rejected.length, 1);
    assert.equal(disc.source, "backend");
    assert.equal(disc.contractVersion, "m64.1");
  });

  it("fetchModuleDiscovery propagates a classified auth error", async () => {
    const platFn = async () => { const e = new Error("no"); e.status = 401; throw e; };
    await assert.rejects(() => fetchModuleDiscovery({ token: "t", platFn }));
  });
});

// ── bootstrap state machine ─────────────────────────────────────────────────
describe("bootstrap state machine", () => {
  it("no token → AUTH_REQUIRED", () => {
    const s = bootReducer(initialBootState(), { type: "NO_TOKEN" });
    assert.equal(s.phase, BOOT.AUTH_REQUIRED);
  });

  it("happy path → READY with modules", () => {
    let s = initialBootState();
    s = bootReducer(s, { type: "HAVE_TOKEN" });
    s = bootReducer(s, { type: "CONTEXT_READY" });
    s = bootReducer(s, { type: "MODULES_OK", payload: { modules: [normalizeModule(backendModule())], cards: [], navigation: null, contractVersion: "m64.1" } });
    assert.equal(s.phase, BOOT.READY);
    assert.equal(s.modules.length, 1);
    assert.ok(canRenderModules(s.phase));
  });

  it("degraded module → DEGRADED phase", () => {
    let s = bootReducer(initialBootState(), { type: "MODULES_OK", payload: { modules: [normalizeModule(backendModule({ state: "degraded" }))] } });
    assert.equal(s.phase, BOOT.DEGRADED);
  });

  it("error categories map to distinct phases and CLEAR modules", () => {
    const withMods = bootReducer(initialBootState(), { type: "MODULES_OK", payload: { modules: [normalizeModule(backendModule())] } });
    assert.equal(bootReducer(withMods, { type: "MODULES_ERR", category: "session_expired" }).phase, BOOT.SESSION_EXPIRED);
    assert.equal(bootReducer(withMods, { type: "MODULES_ERR", category: "permission_restricted" }).phase, BOOT.PERMISSION_RESTRICTED);
    assert.equal(bootReducer(withMods, { type: "MODULES_ERR", category: "network" }).phase, BOOT.OFFLINE);
    const errd = bootReducer(withMods, { type: "MODULES_ERR", category: "server_error" });
    assert.equal(errd.phase, BOOT.ERROR);
    assert.equal(errd.modules.length, 0); // never keep stale modules on failure
  });

  it("logout clears module state", () => {
    let s = bootReducer(initialBootState(), { type: "MODULES_OK", payload: { modules: [normalizeModule(backendModule())] } });
    s = bootReducer(s, { type: "LOGOUT" });
    assert.equal(s.phase, BOOT.AUTH_REQUIRED);
    assert.equal(s.modules.length, 0);
  });

  it("context switch invalidates prior module state (no cross-tenant flash)", () => {
    let s = bootReducer(initialBootState(), { type: "MODULES_OK", payload: { modules: [normalizeModule(backendModule())] } });
    s = bootReducer(s, { type: "CONTEXT_SWITCH" });
    assert.equal(s.phase, BOOT.LOADING_MODULES);
    assert.equal(s.modules.length, 0);
  });
});

// ── drift detection ─────────────────────────────────────────────────────────
describe("registry drift detection", () => {
  const local = [{ id: "trading", version: "62.9", status: "enabled", permissions: ["paper_account"], capabilities: ["paper_trading"], routes: ["/trading"] }];

  it("no drift when backend matches mirror", () => {
    const backend = [normalizeModule(backendModule())];
    const r = detectDrift(backend, local);
    assert.equal(r.drift.length, 0);
    assert.equal(r.hasCritical, false);
    assert.equal(driftSummary(r), "no drift");
  });

  it("placeholder falsely marked implemented is CRITICAL", () => {
    const backend = [normalizeModule(backendModule({ implemented: false }))];
    const r = detectDrift(backend, local);
    assert.ok(r.hasCritical);
    assert.ok(r.drift.some((d) => d.field === "implemented" && d.severity === "critical"));
  });

  it("capability mismatch is CRITICAL; version mismatch is info", () => {
    const backend = [normalizeModule(backendModule({ capabilities: ["x"], version: "99.0" }))];
    const r = detectDrift(backend, local);
    assert.ok(r.drift.some((d) => d.field === "capabilities" && d.severity === "critical"));
    assert.ok(r.drift.some((d) => d.field === "version" && d.severity === "info"));
  });

  it("module only in backend or only in mirror is flagged", () => {
    const r = detectDrift([normalizeModule(backendModule({ id: "new" }))], local);
    assert.ok(r.drift.some((d) => d.field === "presence"));
  });
});

// ── guard ───────────────────────────────────────────────────────────────────
describe("module route guard (UX only)", () => {
  const modules = [
    normalizeModule(backendModule()),
    normalizeModule(backendModule({ id: "ielts", name: "IELTS", state: "not_implemented", enabled: false, implemented: false, routes: [] })),
    normalizeModule(backendModule({ id: "restricted", name: "R", state: "permission_restricted" })),
  ];
  const shell = { authenticated: true, modules };

  it("available → allow", () => assert.equal(evaluateModuleRoute(shell, "trading").outcome, GUARD.ALLOW));
  it("placeholder → not_implemented", () => assert.equal(evaluateModuleRoute(shell, "ielts").outcome, GUARD.NOT_IMPLEMENTED));
  it("restricted → permission_restricted", () => assert.equal(evaluateModuleRoute(shell, "restricted").outcome, GUARD.PERMISSION_RESTRICTED));
  it("unknown → not_found", () => assert.equal(evaluateModuleRoute(shell, "nope").outcome, GUARD.NOT_FOUND));
  it("unauthenticated → auth_required", () => assert.equal(evaluateModuleRoute({ authenticated: false, modules }, "trading").outcome, GUARD.AUTH_REQUIRED));
  it("production pathname guard resolves backend-owned routes only", () => {
    assert.equal(moduleForPath(modules, "/trading/orders")?.id, "trading");
    assert.equal(evaluateModulePath(shell, "/trading/orders").outcome, GUARD.ALLOW);
    assert.equal(evaluateModulePath(shell, "/unowned"), null);
  });
});

// ── icons ─────────────────────────────────────────────────────────────────────
describe("safe icon mapping", () => {
  it("known icon passes through", () => assert.equal(safeIcon("◈"), "◈"));
  it("unknown/hostile icon falls back (no code execution possible)", () => {
    assert.equal(safeIcon("<script>alert(1)</script>"), FALLBACK_ICON);
    assert.equal(safeIcon("__proto__"), FALLBACK_ICON);
    assert.equal(safeIcon(123), FALLBACK_ICON);
  });
});

// ── shell backend navigation ────────────────────────────────────────────────
describe("backend-driven navigation", () => {
  const backendNav = {
    group: "applications",
    modules: [
      { id: "trading", label: "Trading", icon: "◈", state: "available", actionable: true, items: [{ id: "t", label: "Overview", href: "/trading" }] },
      { id: "ielts", label: "IELTS", icon: "✦", state: "not_implemented", actionable: false, items: [{ id: "i", label: "IELTS", href: "/ielts" }] },
    ],
  };

  it("actionable module gets a live href; non-actionable does not", () => {
    const g = applicationsGroupFromBackend(backendNav);
    const t = g.items.find((i) => i.id === "trading");
    const i = g.items.find((i) => i.id === "ielts");
    assert.equal(t.href, "/trading");
    assert.equal(t.actionable, true);
    assert.equal(i.href, null);
    assert.equal(i.badge, "soon");
  });

  it("full shell nav keeps platform groups + adds backend Applications + Admin", () => {
    const nav = getShellNavigationFromBackend(backendNav);
    assert.equal(nav.platform.length, NAV_GROUPS.length);
    assert.equal(nav.applications.source, "backend");
    assert.equal(nav.administration.id, "administration");
  });

  it("mirror cannot grant an actionable route the backend did not", () => {
    // backend says not actionable → composed nav must not produce a live link
    const g = applicationsGroupFromBackend({ modules: [{ id: "x", label: "X", state: "permission_restricted", actionable: false, items: [{ href: "/x" }] }] });
    assert.equal(g.items[0].href, null);
  });

  it("command palette includes only actionable backend applications", () => {
    const commands = applicationCommandsFromBackend(backendNav);
    assert.deepEqual(commands.map((c) => c.route), ["/trading"]);
  });
});
