/**
 * Backend voice sessions must not be stranded by client-side teardown.
 *
 * Reproduced on a throwaway database before any code changed: `POST /stop`
 * moves only `input_state` (recording → processing) and leaves the
 * conversation in LISTENING, while route change, provider unmount, hard
 * reset, logout and recognition errors sent the backend nothing at all. Each
 * abandoned session stayed active, every talk cycle opened another, and at
 * eight the per-user budget answered 409 RESOURCE_BUDGET_EXHAUSTED — voice
 * stopped working entirely.
 *
 * The backend already had the terminal operation: `POST /finish` moves the
 * session to FINISHED, is idempotent, 404s an unknown id, 401s without
 * authentication, and keeps the historical row. Nothing called it. This is the
 * client half of that contract.
 */
import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { createSessionFinalizer } from "./index.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const PROVIDER = join(HERE, "..", "..", "components", "voice", "VoiceRuntimeProvider.jsx");

/**
 * A backend stand-in with the real endpoint's semantics: finishing moves a
 * session out of LISTENING, repeats are accepted, and the row survives.
 */
function fakeBackend({ failNext = 0, cap = 8 } = {}) {
  const sessions = new Map();
  let seq = 0;
  let failures = failNext;
  const calls = [];

  return {
    calls,
    sessions,
    activeCount() {
      return [...sessions.values()].filter((s) => s.state !== "FINISHED" && s.state !== "FAILED").length;
    },
    historyCount() {
      return sessions.size;
    },
    /** POST /sessions — refuses past the per-user budget, like the backend. */
    createSession(owner = "owner") {
      if (this.activeCount() >= cap) {
        const err = new Error("RESOURCE_BUDGET_EXHAUSTED");
        err.status = 409;
        throw err;
      }
      seq += 1;
      const id = `vses_${seq}`;
      sessions.set(id, { id, owner, state: "LISTENING", inputState: "recording" });
      return id;
    },
    /** POST /stop — input_state only; state deliberately unchanged. */
    stop(id) {
      const s = sessions.get(id);
      if (s) s.inputState = "processing";
    },
    /** POST /finish */
    async finish(token, id, options = {}) {
      calls.push({ token, id, keepalive: Boolean(options.keepalive) });
      if (failures > 0) {
        failures -= 1;
        throw new Error("network unreachable");
      }
      if (!token) {
        const err = new Error("unauthorized");
        err.status = 401;
        throw err;
      }
      const s = sessions.get(id);
      if (!s) {
        const err = new Error("not found");
        err.status = 404;
        throw err;
      }
      if (s.owner !== token) {
        const err = new Error("forbidden");
        err.status = 404; // the backend hides other users' sessions
        throw err;
      }
      s.state = "FINISHED";
      s.inputState = "idle";
      return { session: { session_id: id, state: "FINISHED" } };
    },
  };
}

function finalizerFor(backend, opts = {}) {
  const pendingSeen = [];
  const finalizer = createSessionFinalizer({
    finish: (token, id, options) => backend.finish(token, id, options),
    onPendingChange: (pending) => pendingSeen.push(pending),
    ...opts,
  });
  return { finalizer, pendingSeen };
}

let backend;
let finalizer;
let pendingSeen;

beforeEach(() => {
  backend = fakeBackend();
  ({ finalizer, pendingSeen } = finalizerFor(backend));
});

/* ------------------------------------------------------------------ */
/* every teardown path terminates the backend session                   */
/* ------------------------------------------------------------------ */

describe("teardown reaches the backend", () => {
  const reasons = ["USER_STOP", "SESSION_CLOSE", "LOGOUT", "UNMOUNT", "ERROR"];

  for (const reason of reasons) {
    it(`${reason} transitions the session out of LISTENING`, async () => {
      const id = backend.createSession("owner");
      backend.stop(id);
      assert.equal(backend.sessions.get(id).state, "LISTENING", "stop alone leaves it listening");

      finalizer.finalize({ token: "owner", sessionId: id, reason });
      await finalizer.whenSettled();

      assert.equal(backend.sessions.get(id).state, "FINISHED");
      assert.equal(backend.activeCount(), 0);
    });
  }

  it("keeps the historical record after terminating", async () => {
    const id = backend.createSession("owner");
    finalizer.finalize({ token: "owner", sessionId: id, reason: "USER_STOP" });
    await finalizer.whenSettled();
    assert.equal(backend.historyCount(), 1, "audit history is preserved, not deleted");
    assert.equal(backend.sessions.get(id).state, "FINISHED");
  });
});

/* ------------------------------------------------------------------ */
/* the budget                                                           */
/* ------------------------------------------------------------------ */

describe("repeated cycles stay under the active-session cap", () => {
  for (const cycles of [5, 10]) {
    it(`${cycles} sequential cycles never accumulate active sessions`, async () => {
      let peak = 0;
      for (let i = 0; i < cycles; i += 1) {
        const id = backend.createSession("owner");
        peak = Math.max(peak, backend.activeCount());
        backend.stop(id);
        finalizer.finalize({ token: "owner", sessionId: id, reason: "USER_STOP" });
        await finalizer.whenSettled();
        assert.equal(backend.activeCount(), 0, `cycle ${i} left a session active`);
      }
      assert.equal(peak, 1, "never more than the one live session");
      assert.equal(backend.historyCount(), cycles, "every cycle is still on record");
    });
  }

  it("without terminal cleanup the cap is reached — the defect this fixes", () => {
    // The pre-fix behaviour, asserted so the regression is unmistakable.
    for (let i = 0; i < 8; i += 1) backend.stop(backend.createSession("owner"));
    assert.equal(backend.activeCount(), 8);
    assert.throws(() => backend.createSession("owner"), /RESOURCE_BUDGET_EXHAUSTED/);
  });
});

/* ------------------------------------------------------------------ */
/* idempotency, scoping, and truthful failure                           */
/* ------------------------------------------------------------------ */

describe("terminal cleanup is safe to repeat", () => {
  it("overlapping teardown paths send one request", async () => {
    const id = backend.createSession("owner");
    assert.equal(finalizer.finalize({ token: "owner", sessionId: id, reason: "SESSION_CLOSE" }), "sent");
    assert.equal(finalizer.finalize({ token: "owner", sessionId: id, reason: "UNMOUNT" }), "in_flight");
    await finalizer.whenSettled();
    assert.equal(finalizer.finalize({ token: "owner", sessionId: id, reason: "LOGOUT" }), "already_finalized");
    assert.equal(backend.calls.length, 1);
  });

  it("skips when there is no session or no token", () => {
    assert.equal(finalizer.finalize({ token: "owner", sessionId: "" }), "skipped");
    assert.equal(finalizer.finalize({ token: "", sessionId: "vses_1" }), "skipped");
    assert.equal(backend.calls.length, 0);
  });

  it("never throws out of a synchronous teardown path", async () => {
    const id = backend.createSession("owner");
    assert.doesNotThrow(() => finalizer.finalize({ token: "owner", sessionId: id }));
    const hostile = createSessionFinalizer({
      finish: () => {
        throw new Error("synchronous explosion");
      },
    });
    assert.doesNotThrow(() => hostile.finalize({ token: "t", sessionId: "vses_x" }));
    await hostile.whenSettled();
    assert.equal(hostile.getPending().length, 1, "a thrown request is pending, not lost");
  });
});

describe("cleanup is authenticated and scoped", () => {
  it("carries the caller's token", async () => {
    const id = backend.createSession("owner");
    finalizer.finalize({ token: "owner", sessionId: id, reason: "USER_STOP" });
    await finalizer.whenSettled();
    assert.equal(backend.calls[0].token, "owner");
  });

  it("passes keepalive only when the page is going away", async () => {
    const a = backend.createSession("owner");
    finalizer.finalize({ token: "owner", sessionId: a, reason: "USER_STOP" });
    await finalizer.whenSettled();
    assert.equal(backend.calls.at(-1).keepalive, false);

    const b = backend.createSession("owner");
    finalizer.finalize({ token: "owner", sessionId: b, reason: "PAGE_HIDE", keepalive: true });
    await finalizer.whenSettled();
    assert.equal(backend.calls.at(-1).keepalive, true);
  });

  it("an unauthenticated attempt does not terminate anything", async () => {
    const id = backend.createSession("owner");
    // finalize() refuses to send without a token, and the backend refuses too.
    assert.equal(finalizer.finalize({ token: "", sessionId: id }), "skipped");
    await assert.rejects(() => backend.finish("", id), /unauthorized/);
    assert.equal(backend.sessions.get(id).state, "LISTENING");
  });

  it("one user cannot terminate another user's session", async () => {
    const victim = backend.createSession("owner-a");
    finalizer.finalize({ token: "owner-b", sessionId: victim, reason: "USER_STOP" });
    await finalizer.whenSettled();
    assert.equal(backend.sessions.get(victim).state, "LISTENING", "the other user's session survives");
    assert.equal(finalizer.getPending().length, 1, "and the failure is reported, not swallowed");
  });

  it("terminating an unknown session is a reported failure, not a silent success", async () => {
    finalizer.finalize({ token: "owner", sessionId: "vses_missing", reason: "USER_STOP" });
    await finalizer.whenSettled();
    assert.equal(finalizer.isFinalized("vses_missing"), false);
    assert.equal(finalizer.getPending()[0].sessionId, "vses_missing");
  });
});

describe("a failed terminal request is pending, never done", () => {
  it("reports the session as still possibly active", async () => {
    const offline = fakeBackend({ failNext: 1 });
    const { finalizer: f, pendingSeen: seen } = finalizerFor(offline);
    const id = offline.createSession("owner");

    f.finalize({ token: "owner", sessionId: id, reason: "SESSION_CLOSE" });
    await f.whenSettled();

    assert.equal(f.isFinalized(id), false, "a dropped request must not claim success");
    const [entry] = f.getPending();
    assert.equal(entry.sessionId, id);
    assert.match(entry.lastError, /network unreachable/);
    assert.equal(offline.sessions.get(id).state, "LISTENING", "the backend really is still active");
    assert.ok(seen.length > 0, "the pending state is published to the UI");
  });

  it("a retry clears it and the session really does finish", async () => {
    const offline = fakeBackend({ failNext: 1 });
    const { finalizer: f } = finalizerFor(offline);
    const id = offline.createSession("owner");
    f.finalize({ token: "owner", sessionId: id, reason: "SESSION_CLOSE" });
    await f.whenSettled();
    assert.equal(f.getPending().length, 1);

    assert.equal(f.retryPending({ token: "owner" }), 1);
    await f.whenSettled();

    assert.deepEqual(f.getPending(), []);
    assert.equal(f.isFinalized(id), true);
    assert.equal(offline.sessions.get(id).state, "FINISHED");
  });

  it("retry counts attempts and needs a token", async () => {
    const offline = fakeBackend({ failNext: 2 });
    const { finalizer: f } = finalizerFor(offline);
    const id = offline.createSession("owner");
    f.finalize({ token: "owner", sessionId: id, reason: "SESSION_CLOSE" });
    await f.whenSettled();
    assert.equal(f.retryPending({ token: "" }), 0, "no token, no retry");
    f.retryPending({ token: "owner" });
    await f.whenSettled();
    assert.equal(f.getPending()[0].attempts, 2);
  });
});

/* ------------------------------------------------------------------ */
/* the provider actually uses it                                        */
/* ------------------------------------------------------------------ */

describe("VoiceRuntimeProvider wires terminal cleanup into every exit", () => {
  const source = readFileSync(PROVIDER, "utf8");

  it("creates the finalizer against the finish endpoint", () => {
    assert.match(source, /createSessionFinalizer\(\{/);
    assert.match(source, /voiceRuntimeActions\.finish\(activeToken, sessionId, options\)/);
  });

  for (const [path, reason] of [
    ["hard reset / route change", "SESSION_CLOSE"],
    ["logout / context switch", "LOGOUT"],
    ["unmount", "UNMOUNT"],
    ["explicit stop", "USER_STOP"],
  ]) {
    it(`${path} finalizes the backend session`, () => {
      assert.ok(
        source.includes(`finalizeBackendSession("${reason}"`),
        `${path} must send the terminal request`
      );
    });
  }

  it("logout uses the outgoing token, not the replacement", () => {
    assert.match(source, /finalizeBackendSession\("LOGOUT", tokenRef\.current\)/);
  });

  it("finalizes on page hide so a closed tab cannot strand a session", () => {
    assert.match(source, /window\.addEventListener\("pagehide", onPageHide\)/);
    assert.match(source, /finalizeBackendSession\("PAGE_HIDE", tokenRef\.current, true\)/);
    assert.match(source, /window\.removeEventListener\("pagehide", onPageHide\)/);
  });

  it("flushes pending cleanup before opening another session", () => {
    assert.match(source, /retryPending\(\{ token: activeToken \}\)/);
  });

  it("publishes pending cleanup rather than assuming success", () => {
    assert.match(source, /dispatch\(\{ type: "CLEANUP_PENDING", pending \}\)/);
    assert.match(source, /pendingCleanup: runtime\.pendingCleanup \|\| \[\]/);
  });

  it("changes no execution or trading authority", () => {
    assert.ok(
      !/approval|execution|gateway|trading|order/i.test(
        source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "")
      ),
      "voice teardown must not touch execution or trading paths"
    );
  });
});
