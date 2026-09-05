/**
 * M47.2 navigation integrity + safety unit tests (node:test).
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  NAV_GROUPS,
  GLOBAL_NAV,
  MOBILE_TABS,
  GO_SHORTCUTS,
  getPrimaryAreas,
  getAllNavItems,
  matchNavItem,
  breadcrumbFor,
  validateNavigationModel,
  inferEnvironment,
} from "./navigation.js";
import { DEPARTMENTS } from "./departments.js";

describe("navigation model integrity", () => {
  it("has exactly 4 groups and 15 primary areas", () => {
    assert.equal(NAV_GROUPS.length, 4);
    assert.equal(getPrimaryAreas().length, 15); // +orbit +nepse +analysis
  });

  it("has expected group ids", () => {
    assert.deepEqual(
      NAV_GROUPS.map((g) => g.id),
      ["operate", "work", "business", "system"]
    );
  });

  it("has expected primary routes", () => {
    const hrefs = getPrimaryAreas().map((i) => i.href).sort();
    assert.deepEqual(hrefs, [
      "/",
      "/agents",
      "/analysis",
      "/automation",
      "/business",
      "/command",
      "/knowledge",
      "/missions",
      "/monitoring",
      "/nepse",
      "/orbit",
      "/projects",
      "/security",
      "/studio",
      "/trading",
    ].sort());
  });

  it("validateNavigationModel returns no errors", () => {
    const errors = validateNavigationModel();
    assert.deepEqual(errors, []);
  });

  it("has no duplicate ids or canonical hrefs", () => {
    const ids = getAllNavItems().map((i) => i.id);
    const hrefs = getAllNavItems().map((i) => i.href).filter(Boolean);
    assert.equal(new Set(ids).size, ids.length);
    assert.equal(new Set(hrefs).size, hrefs.length);
  });

  it("aliases do not overwrite another item canonical href as id collision", () => {
    const byHref = new Map(getPrimaryAreas().map((i) => [i.href, i.id]));
    for (const item of getAllNavItems()) {
      for (const a of item.aliases || []) {
        if (byHref.has(a) && byHref.get(a) !== item.id) {
          // alias may point at legacy path that is NOT a primary canonical of another —
          // if it is a primary of another, that is a programming error
          const owner = byHref.get(a);
          assert.notEqual(
            owner,
            undefined
          );
          // Allowed only if alias is intentional redirect of THIS item; primary routes
          // of other items should not appear as aliases of a different area.
          // /control is alias of monitoring; /control is NOT a primary area href. OK.
          if (["/", "/missions", "/studio", "/projects", "/security", "/automation", "/knowledge", "/command", "/agents",
      "/analysis", "/business", "/trading", "/monitoring"].includes(a)) {
            assert.equal(owner, item.id, `alias ${a} collides with primary of ${owner}`);
          }
        }
      }
    }
  });
});

describe("departments CONTROL dedupe", () => {
  it("CONTROL and CONTROL_CENTER share control route; STUDIO_CONTROL is distinct", () => {
    assert.equal(DEPARTMENTS.CONTROL.route, "/control");
    assert.equal(DEPARTMENTS.CONTROL_CENTER.route, "/control");
    assert.equal(DEPARTMENTS.STUDIO_CONTROL.route, "/studio/control-room");
    // Object can only have one CONTROL key — verify no silent dual definition by checking studio key exists
    assert.ok(DEPARTMENTS.STUDIO_CONTROL);
  });
});

describe("matchNavItem + breadcrumb", () => {
  it("matches home and nested missions", () => {
    assert.equal(matchNavItem("/")?.id, "home");
    assert.equal(matchNavItem("/missions")?.id, "missions");
    assert.equal(matchNavItem("/missions/abc/intake")?.id, "missions");
    assert.equal(matchNavItem("/command")?.id, "command");
    assert.equal(matchNavItem("/trading")?.id, "trading");
  });

  it("breadcrumb uses canonical labels", () => {
    const b = breadcrumbFor("/trading");
    assert.equal(b.area, "Trading Guardian");
    assert.match(b.group, /business/i);
  });
});

describe("mobile tabs", () => {
  it("matches M47.2 companion order", () => {
    assert.deepEqual(
      MOBILE_TABS.map((t) => t.id),
      ["home", "approvals", "saathi", "business", "me"]
    );
    assert.equal(MOBILE_TABS.find((t) => t.id === "approvals").href, "/approvals");
    assert.equal(MOBILE_TABS.find((t) => t.id === "business").href, "/business");
    assert.equal(MOBILE_TABS.find((t) => t.id === "me").href, "/settings");
    assert.equal(MOBILE_TABS.find((t) => t.id === "saathi").action, "copilot");
  });
});

describe("go shortcuts", () => {
  it("includes safe go-to map", () => {
    assert.equal(GO_SHORTCUTS.h, "/");
    assert.equal(GO_SHORTCUTS.c, "/command");
    assert.equal(GO_SHORTCUTS.a, "/approvals");
  });
});

describe("environment inference", () => {
  it("classifies local and does not invent production for empty", () => {
    assert.equal(inferEnvironment("http://localhost:8765"), "local");
    assert.equal(inferEnvironment(""), "local");
  });
});

describe("trading safety in nav model", () => {
  it("trading item is risk-flagged and paper-only (M62.8: no live authority)", () => {
    const t = getPrimaryAreas().find((i) => i.id === "trading");
    assert.ok(t);
    assert.equal(t.riskFlag, true);
    assert.equal(t.authoritySensitivity, "paper-only");
    assert.equal(t.environmentSensitivity, "never-imply-production");
    assert.equal(t.href, "/trading");
  });
});

describe("experience mode does not appear in authority fields", () => {
  it("nav items do not grant authority via experience", () => {
    for (const item of getAllNavItems()) {
      assert.equal(item.experienceUnlocks, undefined);
      assert.notEqual(item.authoritySensitivity, "autonomous");
    }
  });
});
