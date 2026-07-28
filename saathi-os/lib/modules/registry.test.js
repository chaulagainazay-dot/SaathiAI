/**
 * M63 — module registry + shell composition tests (node:test).
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  ModuleRegistry,
  defineModule,
  buildDefaultRegistry,
  getRegistry,
  TRADING_MODULE,
  IELTS_MODULE,
  PLACEHOLDER_MODULES,
} from "./registry.js";
import {
  getShellNavigation,
  getDashboard,
  getSearchProviders,
  getWorkspaceViews,
  ADMIN_GROUP,
} from "./shell.js";
import { NAV_GROUPS } from "../navigation.js";

function mini(id = "x", status = "enabled") {
  return {
    id,
    name: id.toUpperCase(),
    version: "1.0.0",
    icon: "●",
    category: "platform",
    status,
    permissions: [id],
    routes: [`/${id}`],
    navItems: [{ id: `${id}-home`, label: id, href: `/${id}` }],
    widgets: [{ id: `${id}-w`, title: "W", kind: "metric" }],
    searchProvider: { providerId: id, objectTypes: ["thing"] },
    workspaceViews: [{ id: `${id}-app`, label: id, scope: "application" }],
  };
}

describe("module registry", () => {
  it("registers and gets modules", () => {
    const r = new ModuleRegistry();
    r.register(mini("a"));
    assert.equal(r.get("a").name, "A");
    assert.equal(r.get("missing"), null);
  });

  it("rejects duplicate registration", () => {
    const r = new ModuleRegistry();
    r.register(mini("a"));
    assert.throws(() => r.register(mini("a")));
  });

  it("rejects missing required fields", () => {
    assert.throws(() => defineModule({ name: "x" }));
  });

  it("enable/disable drives listEnabled", () => {
    const r = new ModuleRegistry();
    r.register(mini("a", "enabled"));
    r.register(mini("b", "placeholder"));
    assert.deepEqual(r.listEnabled().map((m) => m.id), ["a"]);
  });

  it("navigation is data-driven", () => {
    const r = new ModuleRegistry();
    r.register(mini("a"));
    const nav = r.navigation();
    assert.equal(nav.group, "applications");
    assert.equal(nav.modules[0].items[0].href, "/a");
  });

  it("dashboard cards: one per module with health + widgets", () => {
    const r = new ModuleRegistry();
    r.register(mini("a"));
    r.register(mini("b"));
    const cards = r.dashboardCards();
    assert.deepEqual(cards.map((c) => c.moduleId).sort(), ["a", "b"]);
    assert.ok(cards.every((c) => "health" in c && Array.isArray(c.widgets)));
  });

  it("composes widgets, search providers, workspace views", () => {
    const r = new ModuleRegistry();
    r.register(mini("a"));
    assert.ok(r.widgets().some((w) => w.moduleId === "a"));
    assert.deepEqual(r.searchProviders()[0].objectTypes, ["thing"]);
    assert.equal(r.workspaceViews()[0].scope, "application");
  });

  it("permission namespaces are a directory, not a grant", () => {
    const r = new ModuleRegistry();
    r.register(mini("a"));
    assert.deepEqual(r.permissionNamespaces()[0].namespaces, ["a"]);
  });
});

describe("default registry", () => {
  it("has Trading and IELTSAlert enabled", () => {
    const r = buildDefaultRegistry();
    assert.equal(r.get("trading").status, "enabled");
    assert.equal(r.get("trading").health, "healthy");
    assert.deepEqual(r.listEnabled().map((m) => m.id).sort(), ["ielts", "trading"]);
  });

  it("registers 3 remaining metadata-only placeholders", () => {
    const r = buildDefaultRegistry();
    for (const pid of ["hcgpos", "travel", "finance"]) {
      const m = r.get(pid);
      assert.ok(m, pid);
      assert.equal(m.status, "placeholder");
      assert.equal(m.health, "not_implemented");
      assert.equal(m.featureFlags.implemented, false);
    }
    assert.equal(PLACEHOLDER_MODULES.length, 3);
  });

  it("IELTS fallback metadata cannot claim external capabilities", () => {
    assert.equal(IELTS_MODULE.status, "enabled");
    assert.equal(IELTS_MODULE.featureFlags.provider_assisted_scoring, false);
    assert.equal(IELTS_MODULE.featureFlags.official_scoring, false);
    assert.equal(IELTS_MODULE.featureFlags.live_availability, false);
    assert.equal(IELTS_MODULE.featureFlags.payment_settlement, false);
  });

  it("Trading declares no live capability", () => {
    assert.equal(TRADING_MODULE.featureFlags.live_trading, false);
    assert.equal(TRADING_MODULE.featureFlags.real_money, false);
    assert.equal(TRADING_MODULE.featureFlags.external_broker, false);
  });

  it("getRegistry is a stable singleton", () => {
    assert.equal(getRegistry(), getRegistry());
    assert.ok(getRegistry().get("trading"));
  });
});

describe("shell composition", () => {
  it("full navigation = platform groups + Applications + Administration", () => {
    const nav = getShellNavigation(buildDefaultRegistry());
    assert.equal(nav.platform.length, NAV_GROUPS.length); // platform groups unchanged
    assert.equal(nav.applications.id, "applications");
    assert.equal(nav.administration.id, "administration");
    // Applications group is data-driven from the registry (5 modules)
    assert.equal(nav.applications.items.length, 5);
    const trading = nav.applications.items.find((i) => i.id === "trading");
    assert.equal(trading.href, "/trading");
    const ielts = nav.applications.items.find((i) => i.id === "ielts");
    assert.equal(ielts.badge, undefined);
  });

  it("dashboard is module-driven", () => {
    const d = getDashboard(buildDefaultRegistry());
    assert.equal(d.installedCount, 5);
    assert.equal(d.enabledCount, 2);
    assert.ok(d.cards.some((c) => c.moduleId === "trading"));
  });

  it("search + workspace aggregation works", () => {
    const r = buildDefaultRegistry();
    assert.ok(getSearchProviders(r).some((p) => p.providerId === "trading"));
    assert.ok(getWorkspaceViews(r).some((v) => v.scope === "evidence"));
  });

  it("administration group is platform-owned and stable", () => {
    assert.equal(ADMIN_GROUP.id, "administration");
    assert.ok(ADMIN_GROUP.items.length >= 5);
  });
});
