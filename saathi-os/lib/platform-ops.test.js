import assert from "node:assert/strict";
import test from "node:test";

import {
  attentionSeverity,
  canCancelExecution,
  canExportEvidence,
  canPreviewRetention,
  clearedAuthenticatedView,
  EVIDENCE_EXPORT_KINDS,
  isProductionAuthorized,
  isSessionExpiryError,
  requiresDestructiveConfirmation,
  runtimeTone,
  safeAuthorityOptions,
  safetyBadges,
  SESSION_EXPIRED_MESSAGE,
  showsSignInForm,
  uiStateDescriptor,
} from "./platform-ops.js";

test("runtime operations UI treats terminal executions as immutable", () => {
  assert.equal(canCancelExecution({ state: "PAUSED" }), true);
  assert.equal(canCancelExecution({ state: "COMPLETED" }), false);
  assert.equal(canCancelExecution({ state: "TIMED_OUT" }), false);
});

test("binding authority choices cannot exceed the displayed role ceiling", () => {
  assert.deepEqual(safeAuthorityOptions("viewer"), ["READ_ONLY"]);
  assert.deepEqual(safeAuthorityOptions("operator"), ["READ_ONLY", "LOCAL_MUTATION"]);
  assert.equal(safeAuthorityOptions("owner").includes("SECURITY_SENSITIVE"), false);
  assert.equal(safeAuthorityOptions("admin").includes("FINANCIAL_EXECUTION"), false);
});

test("irreversible administration actions require confirmation", () => {
  assert.equal(requiresDestructiveConfirmation("REVOKE_BINDING"), true);
  assert.equal(requiresDestructiveConfirmation("RESOLVE_FAILED"), true);
  assert.equal(requiresDestructiveConfirmation("MARK_REVIEWED"), false);
  assert.equal(runtimeTone("REVOKED"), "error");
});

test("M54 retention preview is owner/admin only", () => {
  assert.equal(canPreviewRetention("viewer"), false);
  assert.equal(canPreviewRetention("operator"), false);
  assert.equal(canPreviewRetention("owner"), true);
  assert.equal(canPreviewRetention("admin"), true);
});

test("M54 evidence export is available to any authenticated platform role", () => {
  assert.equal(canExportEvidence("viewer"), true);
  assert.equal(canExportEvidence("stranger"), false);
  assert.ok(EVIDENCE_EXPORT_KINDS.includes("certification_manifest"));
  assert.ok(!EVIDENCE_EXPORT_KINDS.includes("raw_arguments"));
});

test("M54 production authorization is never honored client-side", () => {
  assert.equal(isProductionAuthorized({ environment: { production_authorized: true } }), false);
  assert.equal(isProductionAuthorized(null), false);
});

test("M54 attention severity ranks uncertain dispatch as critical", () => {
  assert.equal(attentionSeverity("DISPATCH_OUTCOME_UNCERTAIN"), "critical");
  assert.equal(attentionSeverity("APPROVAL_REQUIRED"), "info");
  assert.equal(attentionSeverity("BINDING_SUSPENDED"), "warn");
});

test("M54 UI state descriptors cover all required operator states", () => {
  for (const key of [
    "loading", "empty", "denied", "SUSPENDED", "REVOKED", "WAITING_APPROVAL",
    "PAUSED", "UNCERTAIN", "FAILED", "CANCELLED", "TIMED_OUT", "COMPLETED",
  ]) {
    assert.ok(uiStateDescriptor(key).label, `${key} has a label`);
  }
  assert.equal(uiStateDescriptor("COMPLETED").tone, "ok");
});

test("M54 safety badges always assert disabled execution surfaces", () => {
  const badges = safetyBadges({ safety: {} }).map((b) => b.label).join(" ");
  assert.ok(badges.includes("DISABLED"));
  assert.ok(badges.includes("DRY_RUN_ONLY"));
  assert.ok(badges.includes("UNENGAGED_ADVISORY_ONLY"));
});

/* ── expired-session recovery ─────────────────────────────────────────────
   Regression cover for the dead-end defect: an idle-expired platform session
   rendered a raw "Platform error" and kept the dead token, so the `!token`
   sign-in branch never rendered and the owner could not re-authenticate
   without clearing localStorage by hand. */

/** Mirror of the page's persist(): the only thing that owns the token. */
function makeSession(token = "tok_live") {
  return {
    token,
    view: { me: { user_id: "usr_1" }, projects: [{ project_id: "p1" }] },
    persist(t) {
      this.token = t;
    },
    recover() {
      this.view = clearedAuthenticatedView();
      this.persist("");
    },
    /** What the page does on an authenticated failure. */
    onAuthedError(error) {
      if (isSessionExpiryError(error, { authenticated: true })) this.recover();
      return this.token;
    },
  };
}

const httpError = (message, status) => Object.assign(new Error(message), { status });

test("expired session clears the token and exposes the sign-in form", () => {
  const s = makeSession();
  assert.equal(showsSignInForm(s.token), false);
  s.onAuthedError(httpError("session expired, revoked, or unknown SESSION_INVALID", 401));
  assert.equal(s.token, "");
  assert.equal(showsSignInForm(s.token), true);
});

test("MEMBERSHIP_REVOKED clears the token", () => {
  const s = makeSession();
  s.onAuthedError(httpError("MEMBERSHIP_REVOKED", 403));
  assert.equal(s.token, "");
  assert.equal(showsSignInForm(s.token), true);
});

test("an authenticated bare 401 clears the token", () => {
  const s = makeSession();
  s.onAuthedError(httpError("Unauthorized", 401));
  assert.equal(s.token, "");
});

test("an unauthenticated 401 is a failed sign-in, not an expiry", () => {
  // The login POST carries no token; a 401 there must not touch stored state.
  assert.equal(isSessionExpiryError(httpError("AUTH_FAILED", 401)), false);
  assert.equal(
    isSessionExpiryError(httpError("AUTH_FAILED", 401), { authenticated: false }),
    false
  );
});

test("403, 500, offline and malformed failures never clear the token", () => {
  for (const error of [
    httpError("forbidden", 403),
    httpError("ROLE_REQUIRED", 403),
    httpError("Internal Server Error", 500),
    httpError("Bad Gateway", 502),
    httpError("Failed to fetch", undefined),
    httpError("NetworkError when attempting to fetch resource", undefined),
    httpError("load failed", undefined),
    httpError("ECONNREFUSED", undefined),
    httpError('{"unexpected":"shape"}', 200),
    new Error("Unexpected token < in JSON at position 0"),
  ]) {
    const s = makeSession();
    s.onAuthedError(error);
    assert.equal(s.token, "tok_live", `must keep token for: ${error.message}`);
    assert.equal(showsSignInForm(s.token), false);
  }
  assert.equal(isSessionExpiryError(null, { authenticated: true }), false);
  assert.equal(isSessionExpiryError(undefined, { authenticated: true }), false);
});

test("a transport failure that mentions a session code still does not clear", () => {
  // An offline blip must never be read as an expiry, whatever the body says.
  assert.equal(
    isSessionExpiryError(httpError("Failed to fetch SESSION_INVALID", 401), {
      authenticated: true,
    }),
    false
  );
});

test("no authenticated user, workspace or org data survives expiry", () => {
  const s = makeSession();
  s.view.me = { user_id: "usr_1", org_id: "org_1", workspace_id: "ws_1" };
  s.onAuthedError(httpError("SESSION_INVALID", 401));

  const blank = clearedAuthenticatedView();
  assert.equal(blank.me, null);
  assert.equal(blank.config, null);
  assert.equal(blank.metrics, null);
  assert.equal(blank.diagnostics, null);
  assert.equal(blank.selectedExecution, null);
  assert.equal(blank.echo, null);
  for (const key of ["projects", "approvals", "bindings", "executions", "attention", "timeline"]) {
    assert.deepEqual(blank[key], [], `${key} must be emptied`);
  }
  assert.equal(JSON.stringify(s.view).includes("usr_1"), false);
  assert.equal(JSON.stringify(s.view).includes("org_1"), false);
  assert.equal(JSON.stringify(s.view).includes("ws_1"), false);
});

test("clearedAuthenticatedView hands back fresh arrays, never a shared one", () => {
  const a = clearedAuthenticatedView();
  a.projects.push("leak");
  assert.deepEqual(clearedAuthenticatedView().projects, []);
});

test("signing in again after expiry recovery restores the platform", () => {
  const s = makeSession();
  s.onAuthedError(httpError("SESSION_INVALID", 401));
  assert.equal(showsSignInForm(s.token), true);

  s.persist("tok_fresh");                       // successful re-login
  assert.equal(s.token, "tok_fresh");
  assert.equal(showsSignInForm(s.token), false);

  // A healthy call after recovery must leave the new session alone.
  s.onAuthedError(httpError("forbidden", 403));
  assert.equal(s.token, "tok_fresh");
});

test("recovery is idempotent, so it cannot drive a refresh loop", () => {
  const s = makeSession();
  s.onAuthedError(httpError("SESSION_INVALID", 401));
  assert.equal(s.token, "");
  // The refresh effect is guarded by `if (token)`, so an empty token stops it.
  s.onAuthedError(httpError("SESSION_INVALID", 401));
  assert.equal(s.token, "");
  assert.equal(showsSignInForm(s.token), true);
});

test("the expiry notice tells the owner what to do without leaking internals", () => {
  assert.match(SESSION_EXPIRED_MESSAGE, /sign in again/i);
  assert.equal(/SESSION_INVALID|token|401/i.test(SESSION_EXPIRED_MESSAGE), false);
});
