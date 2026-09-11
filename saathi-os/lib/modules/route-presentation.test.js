/**
 * SaathiOS UI recovery — regression tests for withheld module-route presentation.
 *
 * Root cause under test: every withheld module route rendered the single loading
 * sentence "Checking application availability…", so an unauthenticated operator
 * (or one whose local API was unreachable) saw a shell whose content area looked
 * permanently hung — no reason, no retry, no sign-in guidance.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { BOOT } from "./bootstrap.js";
import { GUARD } from "./guard.js";
import {
  GATE_ACTION,
  GATE_KIND,
  gateAriaRole,
  presentRouteGate,
} from "./route-presentation.js";

const LOADING_SENTENCE = "Checking application availability…";
const actionIds = (gate) => gate.actions.map((a) => a.id);

test("loading phases are the only ones that say 'checking availability'", () => {
  for (const phase of [BOOT.INITIALIZING, BOOT.LOADING_CONTEXT, BOOT.LOADING_MODULES]) {
    const gate = presentRouteGate({ phase, outcome: null });
    assert.equal(gate.kind, GATE_KIND.LOADING, phase);
    assert.equal(gate.message, LOADING_SENTENCE, phase);
    assert.equal(gateAriaRole(gate.kind), "status", phase);
  }
});

test("terminal phases never present as still loading", () => {
  const terminal = [
    BOOT.AUTH_REQUIRED,
    BOOT.SESSION_EXPIRED,
    BOOT.OFFLINE,
    BOOT.PERMISSION_RESTRICTED,
    BOOT.ERROR,
  ];
  for (const phase of terminal) {
    const gate = presentRouteGate({ phase, outcome: null });
    assert.notEqual(gate.kind, GATE_KIND.LOADING, phase);
    assert.notEqual(gate.message, LOADING_SENTENCE, phase);
    assert.equal(gateAriaRole(gate.kind), "alert", phase);
    assert.ok(gate.message.length > 0, phase);
    assert.ok(gate.actions.length > 0, `${phase} must offer at least one action`);
  }
});

test("unauthenticated route offers sign-in and states invite-only alpha", () => {
  const gate = presentRouteGate({ phase: BOOT.AUTH_REQUIRED, outcome: null });
  assert.equal(gate.kind, GATE_KIND.AUTH);
  assert.deepEqual(actionIds(gate), [GATE_ACTION.SIGN_IN]);
  assert.match(gate.detail, /invite only/i);
  assert.match(gate.detail, /no public sign-up/i);
  const signIn = gate.actions.find((a) => a.id === GATE_ACTION.SIGN_IN);
  assert.equal(signIn.href, "/unlock");
});

test("expired session is distinguished from never having signed in", () => {
  const expired = presentRouteGate({ phase: BOOT.SESSION_EXPIRED, outcome: null });
  const fresh = presentRouteGate({ phase: BOOT.AUTH_REQUIRED, outcome: null });
  assert.equal(expired.kind, GATE_KIND.AUTH);
  assert.notEqual(expired.message, fresh.message);
  assert.match(expired.message, /expired/i);
});

test("unreachable local API renders a degraded state with retry and diagnostics", () => {
  const gate = presentRouteGate({ phase: BOOT.OFFLINE, outcome: null });
  assert.equal(gate.kind, GATE_KIND.OFFLINE);
  assert.ok(actionIds(gate).includes(GATE_ACTION.RETRY));
  assert.ok(actionIds(gate).includes(GATE_ACTION.DIAGNOSTICS));
  // Wording must describe local services, never a live/broker connection.
  assert.match(gate.message, /local platform API/i);
  assert.doesNotMatch(`${gate.title} ${gate.message} ${gate.detail}`, /live|broker|connected/i);
});

test("discovery error is reported as a platform fault, not a permission decision", () => {
  const gate = presentRouteGate({ phase: BOOT.ERROR, outcome: null });
  assert.equal(gate.kind, GATE_KIND.ERROR);
  assert.ok(actionIds(gate).includes(GATE_ACTION.RETRY));
  assert.match(gate.detail, /not a permission decision/i);
});

test("permission restriction never offers retry or sign-in", () => {
  for (const gate of [
    presentRouteGate({ phase: BOOT.PERMISSION_RESTRICTED, outcome: null }),
    presentRouteGate({
      phase: BOOT.READY,
      outcome: { outcome: GUARD.PERMISSION_RESTRICTED },
    }),
  ]) {
    assert.equal(gate.kind, GATE_KIND.RESTRICTED);
    assert.ok(!actionIds(gate).includes(GATE_ACTION.RETRY));
    assert.ok(!actionIds(gate).includes(GATE_ACTION.SIGN_IN));
  }
});

test("a resolved guard outcome wins over the bootstrap phase", () => {
  const gate = presentRouteGate({
    phase: BOOT.READY,
    outcome: { outcome: GUARD.DISABLED },
    moduleName: "Trading Guardian",
  });
  assert.equal(gate.message, "This application is disabled.");
  assert.equal(gate.title, "Trading Guardian");
});

test("every guard denial outcome has a dedicated message", () => {
  const denials = [
    GUARD.AUTH_REQUIRED,
    GUARD.NOT_FOUND,
    GUARD.NOT_IMPLEMENTED,
    GUARD.DISABLED,
    GUARD.PERMISSION_RESTRICTED,
    GUARD.DEGRADED,
    GUARD.UNAVAILABLE,
  ];
  const seen = new Set();
  for (const outcome of denials) {
    const gate = presentRouteGate({ phase: BOOT.READY, outcome: { outcome } });
    assert.notEqual(gate.message, LOADING_SENTENCE, outcome);
    seen.add(gate.message);
  }
  assert.ok(seen.size >= 5, "denial messages must be meaningfully distinct");
});

test("no presentation ever claims a live or broker connection", () => {
  const phases = Object.values(BOOT);
  const outcomes = [null, ...Object.values(GUARD).map((o) => ({ outcome: o }))];
  for (const phase of phases) {
    for (const outcome of outcomes) {
      const gate = presentRouteGate({ phase, outcome });
      const blob = `${gate.title} ${gate.message} ${gate.detail}`;
      assert.doesNotMatch(blob, /LIVE CONNECTED/i, `${phase}/${outcome?.outcome}`);
      assert.doesNotMatch(blob, /broker|order execution|credential/i, `${phase}/${outcome?.outcome}`);
    }
  }
});

test("presentation is total — unknown input still yields a renderable gate", () => {
  const gate = presentRouteGate({});
  assert.ok(gate.title.length > 0);
  assert.ok(gate.message.length > 0);
  assert.ok(Array.isArray(gate.actions));
  const bogus = presentRouteGate({ phase: "NOT_A_PHASE", outcome: { outcome: "nope" } });
  assert.ok(bogus.message.length > 0);
});

test("no gate action links to registration or credential entry", () => {
  for (const phase of Object.values(BOOT)) {
    const gate = presentRouteGate({ phase, outcome: null });
    for (const action of gate.actions) {
      if (!action.href) continue;
      assert.doesNotMatch(action.href, /signup|register|credential|api-key/i);
    }
  }
});
