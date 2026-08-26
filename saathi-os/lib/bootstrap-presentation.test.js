/**
 * The unlock screen must not invent facts about the backend it could not reach.
 *
 * Two halves, because the defect lived across both:
 *
 *   1. the pure decision — `bootstrapPresentation()`, exercised directly;
 *   2. the page integration — `app/unlock/page.jsx`, checked against its own
 *      source. There is no DOM renderer in this suite, and the page pulls in
 *      next/navigation, WebAuthn probes and the design system, so rendering it
 *      here would test the mocks rather than the screen. What can be pinned
 *      statically is exactly what regressed: which value the catch path stores,
 *      and which expression gates the form. The rendered states are verified
 *      live in the browser during validation.
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { bootstrapPresentation, COPY, UNREACHABLE } from "./bootstrap-presentation.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const PAGE_SOURCE = readFileSync(join(HERE, "..", "app", "unlock", "page.jsx"), "utf8");

/** The page with comments removed: prose that *names* the old defect is not the
 *  defect, and a test that reads it would fail on the explanation. */
const PAGE = PAGE_SOURCE
  .replace(/\/\*[\s\S]*?\*\//g, "")
  .replace(/^\s*\/\/.*$/gm, "");

const ARMED = {
  state: "BOOTSTRAP_ARMED",
  bootstrap_available: true,
  bootstrap_enabled: true,
  requires_operator_token: true,
};

describe("bootstrapPresentation — unreachable is its own answer", () => {
  it("a rejected status request renders unreachable, not disabled", () => {
    const view = bootstrapPresentation(UNREACHABLE);
    assert.equal(view.kind, "unreachable");
    assert.match(view.copy, /Cannot reach the SaathiOS platform API/);
    assert.doesNotMatch(view.copy, /Setup is disabled/);
    assert.equal(view.showForm, false);
  });

  it("the unreachable copy names the two things an operator can actually check", () => {
    assert.match(COPY.unreachable, /local server is running/);
    assert.match(COPY.unreachable, /loopback address/);
  });

  it("no unreachable input can reach the configuration-derived disabled copy", () => {
    // Everything the catch path could plausibly store, including the shape that
    // caused the original defect. None may produce "disabled".
    const shapes = [
      UNREACHABLE,
      { unreachable: true },
      { unreachable: true, bootstrap_enabled: false },
      { unreachable: true, state: "BOOTSTRAP_ARMED" },
      { state: "UNKNOWN" },
      {},
    ];
    for (const shape of shapes) {
      const view = bootstrapPresentation(shape);
      assert.notEqual(view.kind, "disabled", JSON.stringify(shape));
      assert.notEqual(view.copy, COPY.disabled, JSON.stringify(shape));
      assert.equal(view.showForm, false, JSON.stringify(shape));
    }
  });
});

describe("bootstrapPresentation — fail closed on absent or malformed data", () => {
  it("null and undefined are loading, not a verdict", () => {
    for (const value of [null, undefined]) {
      const view = bootstrapPresentation(value);
      assert.equal(view.kind, "loading");
      assert.equal(view.showForm, false);
    }
  });

  it("malformed payloads fail closed without rendering the form", () => {
    const malformed = [
      {},
      { state: "" },
      { state: 42 },
      { state: "BOOTSTRAP_ARMED" },                                  // booleans missing
      { state: "BOOTSTRAP_ARMED", bootstrap_available: true },       // enabled missing
      { state: "BOOTSTRAP_ARMED", bootstrap_enabled: true },         // available missing
      { state: "BOOTSTRAP_ARMED", bootstrap_available: "yes", bootstrap_enabled: "yes" },
      { state: "SOMETHING_NEW", bootstrap_available: true, bootstrap_enabled: true },
      "BOOTSTRAP_ARMED",
      42,
    ];
    for (const value of malformed) {
      const view = bootstrapPresentation(value);
      assert.equal(view.kind, "unknown", JSON.stringify(value));
      assert.equal(view.showForm, false, JSON.stringify(value));
    }
  });

  it("missing bootstrap_enabled is never read as bootstrap_enabled:false", () => {
    // The original expression was `!boot.bootstrap_enabled`, which cannot tell
    // "the operator disarmed this" from "we have no idea".
    const view = bootstrapPresentation({ state: "BOOTSTRAP_ARMED", bootstrap_available: true });
    assert.equal(view.kind, "unknown");
    assert.notEqual(view.copy, COPY.disabled);
  });
});

describe("bootstrapPresentation — the states stay distinct", () => {
  it("armed renders the setup form", () => {
    const view = bootstrapPresentation(ARMED);
    assert.equal(view.kind, "armed");
    assert.equal(view.showForm, true);
    assert.equal(view.showPanel, true);
    assert.match(view.copy, /one-time setup token/);
  });

  it("an explicit bootstrap_enabled:false renders disabled", () => {
    const view = bootstrapPresentation({
      state: "UNINITIALIZED",
      bootstrap_available: false,
      bootstrap_enabled: false,
    });
    assert.equal(view.kind, "disabled");
    assert.equal(view.copy, COPY.disabled);
    assert.equal(view.showForm, false);
  });

  it("ACTIVE hides first-time setup entirely", () => {
    const view = bootstrapPresentation({ state: "ACTIVE" });
    assert.equal(view.kind, "active");
    assert.equal(view.showPanel, false);
    assert.equal(view.showForm, false);
  });

  it("a contaminated store is blocked, and says so in its own words", () => {
    const view = bootstrapPresentation({ state: "CONTAMINATED_UNINITIALIZED" });
    assert.equal(view.kind, "contaminated");
    assert.match(view.copy, /credentials but no completed setup/);
    assert.equal(view.showForm, false);
  });

  it("an expired token is distinct from a disarmed installation", () => {
    const view = bootstrapPresentation(ARMED, "BOOTSTRAP_TOKEN_EXPIRED");
    assert.equal(view.kind, "expired");
    assert.notEqual(view.copy, COPY.disabled);
    // Deliberate: the installation is still armed, only the operator's artefact
    // is stale, so the form stays available for the rotated token. The copy has
    // to say that plainly, otherwise the operator re-arms something that was
    // never disarmed.
    assert.equal(view.showForm, true);
    assert.match(view.copy, /expired/i);
    assert.match(view.copy, /Generate a new one on this machine/);
  });

  it("an expiry refusal cannot resurrect a state that is not armed", () => {
    for (const status of [UNREACHABLE, { state: "ACTIVE" }, { state: "CONTAMINATED_UNINITIALIZED" },
                          { state: "UNINITIALIZED", bootstrap_enabled: false }]) {
      const view = bootstrapPresentation(status, "BOOTSTRAP_TOKEN_EXPIRED");
      assert.notEqual(view.kind, "expired", JSON.stringify(status));
    }
  });

  it("every kind has copy, and only armed/expired show the form", () => {
    const cases = [
      [null, "loading"],
      [UNREACHABLE, "unreachable"],
      [{}, "unknown"],
      [ARMED, "armed"],
      [{ state: "UNINITIALIZED", bootstrap_enabled: false }, "disabled"],
      [{ state: "ACTIVE" }, "active"],
      [{ state: "CONTAMINATED_UNINITIALIZED" }, "contaminated"],
    ];
    const seen = new Set();
    for (const [status, kind] of cases) {
      const view = bootstrapPresentation(status);
      assert.equal(view.kind, kind);
      assert.equal(typeof view.copy, "string");
      assert.ok(view.copy.length > 0, kind);
      assert.equal(view.showForm, kind === "armed", `showForm wrong for ${kind}`);
      seen.add(view.copy);
    }
    assert.equal(seen.size, cases.length, "each state must read differently");
  });
});

describe("unlock page integration", () => {
  it("stores UNREACHABLE on a rejected status request, never a status-shaped object", () => {
    assert.ok(PAGE.includes("setBoot(UNREACHABLE)"), "catch must store the sentinel");
    assert.ok(
      !/catch\s*\(\s*\)\s*=>\s*setBoot\(\s*\{/.test(PAGE),
      'no catch may synthesise a status object such as {state: "UNKNOWN"}',
    );
    assert.ok(!PAGE.includes('setBoot({ state: "UNKNOWN" })'));
  });

  it("no bootstrap status request rejects silently", () => {
    // A `.catch(() => {})` leaves `boot` at its previous value, so a refresh
    // that fails would keep showing the state from before it failed.
    const calls = PAGE.match(/bootstrapStatus\(\)[^;]*/g) || [];
    assert.ok(calls.length > 0);
    for (const call of calls) {
      assert.match(call, /\.catch\(\(\) => setBoot\(UNREACHABLE\)\)/, call);
    }
  });

  it("the panel renders decided copy and never re-derives it", () => {
    assert.ok(PAGE.includes("{bootView.copy}"), "copy comes from the decision");
    assert.ok(!PAGE.includes("!boot.bootstrap_enabled"), "the original defect must not return");
    assert.ok(!PAGE.includes("boot.bootstrap_available"), "the form gate must not be re-derived");
    assert.ok(!/"Setup is disabled/.test(PAGE), "disabled copy belongs to the module");
  });

  it("the form and the panel are gated only by the decision", () => {
    assert.ok(PAGE.includes("{bootView.showForm && ("), "form gated by showForm");
    assert.ok(PAGE.includes("{bootView.showPanel && ("), "panel gated by showPanel");
    assert.ok(PAGE.includes('bootView.kind === "active"'), "sign-in gated by the decided kind");
  });

  it("neither secret is persisted or logged by the page", () => {
    assert.ok(!/localStorage\.setItem\(\s*["'][^"']*(token|password)/i.test(PAGE));
    assert.ok(!/sessionStorage/.test(PAGE));
    assert.ok(!/console\.(log|info|warn|error)\s*\([^)]*(opToken|np\b|password)/i.test(PAGE));
    assert.ok(PAGE.includes('setOpToken("")'), "the operator token is cleared after submit");
  });
});
