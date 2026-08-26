/**
 * R2.1-D17 — one bounded recovery from an idle-expired derived platform session.
 *
 * The physical microphone test failed with the dock reading "session expired,
 * revoked, or unknown" and a mic-attempt count of one that never reached the
 * device. The derived platform session's one-hour idle TTL had closed while the
 * canonical owner session behind it was still valid for another fourteen hours.
 * The TTL is a security control and is unchanged; what is repaired is the client
 * lifecycle that had no way to ask for a new derived session.
 *
 * These tests pin the shape of that recovery: which failure triggers it, how
 * many times it may happen, what it does with the stale token, and — most
 * importantly — everything it must refuse to do.
 */
import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import {
  RECOVERABLE_CODE,
  isRecoverableSessionFailure,
  exchangeForFreshPlatformSession,
  withPlatformSessionRecovery,
  resetPlatformSessionRecovery,
} from "./platform-session-recovery.js";

const STALE = "stale-platform-token";
const FRESH = "fresh-platform-token";

function sessionInvalid() {
  const e = new Error("session expired, revoked, or unknown");
  e.status = 401;
  e.code = RECOVERABLE_CODE;
  return e;
}

function httpError(status, code = "") {
  const e = new Error(`http ${status}`);
  e.status = status;
  e.code = code;
  return e;
}

/** Records everything the boundary did, so ordering can be asserted. */
function harness({ attemptResults, exchangeResult }) {
  const log = [];
  const state = { token: STALE };
  let attemptIndex = 0;
  return {
    log,
    state,
    attempt: async (tok) => {
      log.push({ ev: "attempt", token: tok });
      const outcome = attemptResults[attemptIndex++];
      if (typeof outcome === "function") throw outcome();
      return outcome;
    },
    opts: {
      exchange: async () => {
        log.push({ ev: "exchange", tokenAtCall: state.token });
        if (typeof exchangeResult === "function") return exchangeResult();
        return exchangeResult;
      },
      storeToken: (t) => { log.push({ ev: "store", token: t }); state.token = t; },
      clearToken: () => { log.push({ ev: "clear" }); state.token = ""; },
    },
  };
}

beforeEach(() => resetPlatformSessionRecovery());

describe("which failures are recoverable", () => {
  it("only 401 carrying the exact bounded code", () => {
    assert.equal(isRecoverableSessionFailure(sessionInvalid()), true);
  });

  it("a generic 401 is not", () => {
    assert.equal(isRecoverableSessionFailure(httpError(401)), false);
    assert.equal(isRecoverableSessionFailure(httpError(401, "ANONYMOUS_PROHIBITED")), false);
  });

  it("neither is 403, 500, a network failure or a malformed error", () => {
    for (const e of [httpError(403, RECOVERABLE_CODE), httpError(500),
                     new Error("Failed to fetch"), null, undefined, "SESSION_INVALID", {}]) {
      assert.equal(isRecoverableSessionFailure(e), false);
    }
  });
});

describe("the happy paths", () => {
  it("a live token performs exactly one create and no exchange", async () => {
    const h = harness({ attemptResults: [{ session: { session_id: "s1" } }] });
    const out = await withPlatformSessionRecovery(STALE, h.attempt, h.opts);
    assert.equal(out.session.session_id, "s1");
    assert.deepEqual(h.log.map((e) => e.ev), ["attempt"]);
  });

  it("an idle-expired token exchanges once and retries once, successfully", async () => {
    const h = harness({
      attemptResults: [sessionInvalid, { session: { session_id: "s2" } }],
      exchangeResult: { ok: true, token: FRESH },
    });
    const out = await withPlatformSessionRecovery(STALE, h.attempt, h.opts);
    assert.equal(out.session.session_id, "s2");
    assert.deepEqual(h.log.map((e) => e.ev), ["attempt", "exchange", "store", "attempt"]);
  });

  it("the new token replaces the old one before the retry runs", async () => {
    const h = harness({
      attemptResults: [sessionInvalid, { session: { session_id: "s3" } }],
      exchangeResult: { ok: true, token: FRESH },
    });
    await withPlatformSessionRecovery(STALE, h.attempt, h.opts);
    const storeAt = h.log.findIndex((e) => e.ev === "store");
    const retryAt = h.log.map((e) => e.ev).lastIndexOf("attempt");
    assert.ok(storeAt < retryAt, "token must be stored before the retry");
    assert.equal(h.log[retryAt].token, FRESH, "the retry must use the fresh token");
    assert.notEqual(h.log[retryAt].token, STALE, "the expired token must never be reused");
  });

  it("retries exactly once, never in a loop", async () => {
    const h = harness({
      attemptResults: [sessionInvalid, sessionInvalid, sessionInvalid],
      exchangeResult: { ok: true, token: FRESH },
    });
    await assert.rejects(() => withPlatformSessionRecovery(STALE, h.attempt, h.opts));
    assert.equal(h.log.filter((e) => e.ev === "attempt").length, 2);
    assert.equal(h.log.filter((e) => e.ev === "exchange").length, 1);
  });

  it("a second SESSION_INVALID is terminal and clears the unusable token", async () => {
    const h = harness({
      attemptResults: [sessionInvalid, sessionInvalid],
      exchangeResult: { ok: true, token: FRESH },
    });
    await assert.rejects(() => withPlatformSessionRecovery(STALE, h.attempt, h.opts),
                         (e) => e.code === RECOVERABLE_CODE);
    assert.ok(h.log.some((e) => e.ev === "clear"));
    assert.equal(h.state.token, "");
  });
});

describe("single flight", () => {
  it("two concurrent expiries share one exchange and one new session", async () => {
    let exchanges = 0;
    const opts = {
      exchange: async () => {
        exchanges += 1;
        await new Promise((r) => setTimeout(r, 10));
        return { ok: true, token: FRESH };
      },
      storeToken: () => {},
      clearToken: () => {},
    };
    const attempts = [];
    const attempt = async (tok) => {
      attempts.push(tok);
      if (tok === STALE) throw sessionInvalid();
      return { session: { session_id: "shared" } };
    };
    const [a, b] = await Promise.all([
      withPlatformSessionRecovery(STALE, attempt, opts),
      withPlatformSessionRecovery(STALE, attempt, opts),
    ]);
    assert.equal(a.session.session_id, "shared");
    assert.equal(b.session.session_id, "shared");
    assert.equal(exchanges, 1, "concurrent callers must share one exchange");
  });

  it("a later expiry after the flight settles may exchange again", async () => {
    let exchanges = 0;
    const opts = {
      exchange: async () => { exchanges += 1; return { ok: true, token: FRESH }; },
      storeToken: () => {}, clearToken: () => {},
    };
    const attempt = async (tok) => {
      if (tok === STALE) throw sessionInvalid();
      return { ok: true };
    };
    await withPlatformSessionRecovery(STALE, attempt, opts);
    await withPlatformSessionRecovery(STALE, attempt, opts);
    assert.equal(exchanges, 2, "the single-flight latch must not stick after settling");
  });
});

describe("failing closed", () => {
  it("an invalid canonical session means no retry and no usable token left", async () => {
    const h = harness({
      attemptResults: [sessionInvalid, { session: { session_id: "never" } }],
      exchangeResult: { ok: false, status: 401, code: "CANONICAL_SESSION_INVALID" },
    });
    await assert.rejects(() => withPlatformSessionRecovery(STALE, h.attempt, h.opts),
                         (e) => e.code === "CANONICAL_SESSION_INVALID");
    assert.equal(h.log.filter((e) => e.ev === "attempt").length, 1, "no retry");
    assert.equal(h.state.token, "");
  });

  for (const [label, result] of [
    ["exchange 401", { ok: false, status: 401, code: "CANONICAL_SESSION_REQUIRED" }],
    ["exchange 403", { ok: false, status: 403, code: "CANONICAL_NOT_ACTIVE" }],
    ["exchange 500", { ok: false, status: 500, code: "EXCHANGE_FAILED" }],
    ["exchange unreachable", { ok: false, status: 0, code: "EXCHANGE_UNREACHABLE" }],
    ["malformed: ok without a token", { ok: true }],
    ["malformed: token of the wrong type", { ok: true, token: 42 }],
    ["malformed: empty token", { ok: true, token: "   " }],
    ["malformed: null response", null],
  ]) {
    it(`${label} produces no create retry`, async () => {
      const h = harness({
        attemptResults: [sessionInvalid, { session: { session_id: "never" } }],
        exchangeResult: result,
      });
      await assert.rejects(() => withPlatformSessionRecovery(STALE, h.attempt, h.opts));
      assert.equal(h.log.filter((e) => e.ev === "attempt").length, 1);
    });
  }

  it("an exchange that throws is not swallowed into a retry", async () => {
    const h = harness({
      attemptResults: [sessionInvalid, { session: { session_id: "never" } }],
      exchangeResult: () => { throw new Error("boom"); },
    });
    await assert.rejects(() => withPlatformSessionRecovery(STALE, h.attempt, h.opts));
    assert.equal(h.log.filter((e) => e.ev === "attempt").length, 1);
  });

  it("a missing exchange implementation fails closed rather than retrying", async () => {
    await assert.rejects(() => exchangeForFreshPlatformSession({}));
  });
});

describe("what recovery must never do", () => {
  it("does not exchange on a generic 401", async () => {
    const h = harness({ attemptResults: [() => httpError(401)], exchangeResult: { ok: true, token: FRESH } });
    await assert.rejects(() => withPlatformSessionRecovery(STALE, h.attempt, h.opts));
    assert.equal(h.log.filter((e) => e.ev === "exchange").length, 0);
  });

  it("does not exchange on 403, 500 or a network failure", async () => {
    for (const make of [() => httpError(403, RECOVERABLE_CODE),
                        () => httpError(500),
                        () => new Error("Failed to fetch")]) {
      resetPlatformSessionRecovery();
      const h = harness({ attemptResults: [make], exchangeResult: { ok: true, token: FRESH } });
      await assert.rejects(() => withPlatformSessionRecovery(STALE, h.attempt, h.opts));
      assert.equal(h.log.filter((e) => e.ev === "exchange").length, 0);
    }
  });

  it("propagates the original error untouched when it is not recoverable", async () => {
    const h = harness({ attemptResults: [() => httpError(500, "INTERNAL")] });
    await assert.rejects(() => withPlatformSessionRecovery(STALE, h.attempt, h.opts),
                         (e) => e.status === 500 && e.code === "INTERNAL");
  });
});

describe("the boundary this is wired into", () => {
  const HERE = dirname(fileURLToPath(import.meta.url));
  const PROVIDER = readFileSync(
    join(HERE, "..", "..", "components", "voice", "VoiceRuntimeProvider.jsx"), "utf8");
  const code = PROVIDER.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

  it("recovery wraps runtime-session creation and nothing else", () => {
    assert.ok(code.includes("withPlatformSessionRecovery"));
    const wrapped = code.slice(code.indexOf("withPlatformSessionRecovery"));
    assert.ok(wrapped.includes("voiceRuntimeActions.createSession"));
    // Not a global interceptor: exactly one call site, plus its import.
    const uses = code.split("withPlatformSessionRecovery").length - 1;
    const imports = code.split(/import[^;]*withPlatformSessionRecovery[^;]*;/).length - 1;
    assert.equal(uses - imports, 1, "exactly one wrapped call site");
    for (const call of ["listen(", "cancel(", "finish(", "transcript("]) {
      const at = code.indexOf(`voiceRuntimeActions.${call}`);
      if (at === -1) continue;
      assert.ok(!code.slice(Math.max(0, at - 200), at).includes("withPlatformSessionRecovery"));
    }
  });

  it("the microphone is claimed only after session creation returns", () => {
    // First occurrences, inside the start handler. Searching from an offset
    // would still find a later call after a mutation moved the claim earlier,
    // which is exactly the regression this guards.
    // Anchored on the start handler's unique opener: "setBusy(true)" appears in
    // several handlers, and the first one is not this one.
    const handler = code.slice(code.indexOf("voiceSession?.openSession?.("));
    const body = handler.slice(0, handler.indexOf("} finally"));
    const ensureAt = body.indexOf("ensureSession(");
    const listenAt = body.indexOf("startListening(");
    assert.ok(ensureAt > -1, "the start handler must create the runtime session");
    assert.ok(listenAt > -1, "the start handler must start listening");
    assert.ok(ensureAt < listenAt,
              "the device claim must not precede runtime-session creation");
    assert.ok(!body.slice(0, ensureAt).includes("getUserMedia"),
              "nothing before session creation may open the device");
  });

  it("the exchange endpoint is the existing D15 provisioning route", () => {
    const api = readFileSync(join(HERE, "..", "api.js"), "utf8");
    assert.ok(api.includes("/api/v1/platform/bootstrap"));
    assert.ok(api.includes("export async function exchangePlatformSession"));
    // No new credential type is introduced anywhere in the recovery path.
    for (const banned of ["password", "operator_token", "bootstrap_token"]) {
      const from = api.indexOf("export async function exchangePlatformSession");
      const next = api.indexOf("export ", from + 40);
      // Comments stripped: the following function's *comment* mentions a
      // password, and a check that reads prose fails on the neighbour's
      // documentation rather than on this function's behaviour.
      const fn = api.slice(from, next === -1 ? undefined : next)
        .replace(/\/\*[\s\S]*?\*\//g, "")
        .replace(/^\s*\/\/.*$/gm, "");
      assert.ok(!fn.includes(banned), banned);
    }
  });
});
