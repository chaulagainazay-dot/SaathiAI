// Reproducible Phase-D evidence: exercises the REAL production afetch +
// classifyRequest (from saathi-os/lib) — NOT mocked — to certify:
//   * a 401'd request is issued exactly once (no retry / no silent replay)
//   * the stale token is cleared once
//   * REQUIRES_USER_REISSUE vs SAFE_TO_RETRY classification
//   * auth-endpoint 401s (wrong password) do NOT trigger recovery
//
// Self-contained: copies the two real modules to a temp dir and only rewrites
// the extensionless `./api` import so Node ESM can resolve it (logic unchanged).
// Run: node scripts/cert/certify_afetch_replay.mjs
import assert from "node:assert";
import { mkdtempSync, copyFileSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const LIB = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "saathi-os", "lib");
const tmp = mkdtempSync(join(tmpdir(), "saathi-cert-"));
copyFileSync(join(LIB, "api.js"), join(tmp, "api.js"));
const authSrc = readFileSync(join(LIB, "authState.js"), "utf8").replace(/from "\.\/api"/g, 'from "./api.js"');
writeFileSync(join(tmp, "authState.js"), authSrc);

// ---- browser globals afetch/authState reference (stubbed; NOT the fetch under test)
const store = new Map();
globalThis.localStorage = {
  getItem: (k) => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => store.set(k, String(v)),
  removeItem: (k) => store.delete(k),
};
// real multi-listener window; count the CANONICAL saathi:auth-required event
let evCount = 0;
const listeners = new Map();
globalThis.window = {
  addEventListener: (t, f) => { (listeners.get(t) || listeners.set(t, new Set()).get(t)).add(f); },
  dispatchEvent: (e) => { if (e.type === "saathi:auth-required") evCount++; (listeners.get(e.type) || []).forEach((f) => f(e)); return true; },
};
globalThis.CustomEvent = class { constructor(t, o) { this.type = t; this.detail = o?.detail; } };

let fetchCalls = [];
globalThis.fetch = async (url, opts = {}) => {
  fetchCalls.push({ url: String(url), method: (opts.method || "GET").toUpperCase() });
  return { status: 401, ok: false, json: async () => ({ error: "unauthorized" }) };
};

const { afetch } = await import(join(tmp, "api.js"));
const { classifyRequest } = await import(join(tmp, "authState.js"));

let pass = 0, fail = 0;
const ok = (name, cond) => { cond ? pass++ : fail++; console.log(cond ? "PASS" : "FAIL", name); };
const B = "http://127.0.0.1:8799";

// Test 1 — mutation 401: one-shot, cleared, one event
store.set("saathi_session", "tok"); fetchCalls = []; evCount = 0;
const res = await afetch(`${B}/api/v1/chat/conversations`, { method: "POST", body: "{}" });
ok("mutation 401 returned to caller", res.status === 401);
ok("afetch made exactly ONE network call (no retry/replay)", fetchCalls.length === 1);
ok("stale token cleared after 401", !store.get("saathi_session"));
ok("one auth-required event for one in-flight request", evCount === 1);

// Test 2 — no background re-issue
const before = fetchCalls.length;
await new Promise((r) => setTimeout(r, 200));
ok("no automatic re-issue after 401", fetchCalls.length === before);

// Test 3 — replay policy classification
ok("POST /chat/conversations = REQUIRES_USER_REISSUE", classifyRequest("POST", "/api/v1/chat/conversations") === "REQUIRES_USER_REISSUE");
ok("POST /connectors/execute = REQUIRES_USER_REISSUE", classifyRequest("POST", "/api/v1/connectors/execute") === "REQUIRES_USER_REISSUE");
ok("POST /trading/order = REQUIRES_USER_REISSUE", classifyRequest("POST", "/api/v1/trading/order") === "REQUIRES_USER_REISSUE");
ok("POST /voice/enroll = REQUIRES_USER_REISSUE (biometric)", classifyRequest("POST", "/api/v1/voice/enroll") === "REQUIRES_USER_REISSUE");
ok("GET /missions = SAFE_TO_RETRY", classifyRequest("GET", "/api/v1/missions") === "SAFE_TO_RETRY");

// Test 4 — auth-endpoint 401 must NOT trigger recovery (wrong password != revoked session)
store.set("saathi_session", "tok"); fetchCalls = []; evCount = 0;
await afetch(`${B}/api/v1/auth/login`, { method: "POST", body: "{}" });
ok("wrong-password login 401 does NOT clear token", store.get("saathi_session") === "tok");
ok("wrong-password login 401 fires NO auth-required event", evCount === 0);

console.log(`\nRESULT ${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
