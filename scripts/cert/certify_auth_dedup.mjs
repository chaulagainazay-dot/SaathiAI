// Certifies exactly-once auth-loss signaling under CONCURRENT 401s, using the
// REAL production afetch + authState (not mocked). Self-contained: copies the
// two modules to a temp dir, rewriting only authState's extensionless `./api`
// import so Node ESM resolves it (logic unchanged).
// Run: node scripts/cert/certify_auth_dedup.mjs
import { mkdtempSync, copyFileSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const LIB = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "saathi-os", "lib");
const tmp = mkdtempSync(join(tmpdir(), "saathi-dedup-"));
copyFileSync(join(LIB, "api.js"), join(tmp, "api.js"));
writeFileSync(join(tmp, "authState.js"),
  readFileSync(join(LIB, "authState.js"), "utf8").replace(/from "\.\/api"/g, 'from "./api.js"'));

// ---- browser env: real multi-listener window + localStorage
const store = new Map();
globalThis.localStorage = {
  getItem: (k) => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => store.set(k, String(v)),
  removeItem: (k) => store.delete(k),
};
const listeners = new Map();
globalThis.window = {
  addEventListener: (t, f) => { (listeners.get(t) || listeners.set(t, new Set()).get(t)).add(f); },
  dispatchEvent: (e) => { (listeners.get(e.type) || []).forEach((f) => f(e)); return true; },
};
globalThis.CustomEvent = class { constructor(t, o) { this.type = t; this.detail = o?.detail; } };

// programmable fetch: 401 for protected GETs; 200 for the auth login/probe
let fetchCalls = [];
let authOk = false;
globalThis.fetch = async (url, opts = {}) => {
  const u = String(url), m = (opts.method || "GET").toUpperCase();
  fetchCalls.push({ u, m });
  if (u.includes("/api/v1/auth/login")) return { status: 200, ok: true, json: async () => ({ ok: true, token: "T" + Date.now() }) };
  if (u.includes("/api/v1/auth/session")) return { status: 200, ok: true, json: async () => ({ authenticated: authOk, session: authOk ? { id: "fp", expires_at: 0 } : null }) };
  return { status: 401, ok: false, json: async () => ({ error: "unauthorized" }) };
};

const { afetch } = await import(join(tmp, "api.js"));
const A = await import(join(tmp, "authState.js"));
const B = "http://127.0.0.1:8799";

// observers
let canonicalEvents = 0;
window.addEventListener("saathi:auth-required", () => { canonicalEvents++; });
let enterAuthRequired = 0, last = null;
A.subscribeAuth((snap) => {
  if (snap.state === "AUTH_REQUIRED" && last !== "AUTH_REQUIRED") enterAuthRequired++;
  last = snap.state;
});

let pass = 0, fail = 0;
const ok = (n, c) => { c ? pass++ : fail++; console.log(c ? "PASS" : "FAIL", n); };

async function toAuthenticated() {
  authOk = true;
  await A.signIn("pw", true);
}

// ── Incident 1: AUTHENTICATED → two CONCURRENT token-bearing 401s ──
await toAuthenticated();
ok("state AUTHENTICATED before incident", A.getAuthSnapshot().state === "AUTHENTICATED");
canonicalEvents = 0; enterAuthRequired = 0; fetchCalls = [];
authOk = false; // subsequent protected GETs now 401
const [r1, r2] = await Promise.all([
  afetch(`${B}/api/v1/control/attention`, { method: "GET" }),
  afetch(`${B}/api/v1/evidence`, { method: "GET" }),
]);
ok("both concurrent requests resolved 401", r1.status === 401 && r2.status === 401);
ok("HTTP 401 count >= 2", fetchCalls.filter((c) => c.u.includes("/api/v1/")).length >= 2);
ok("localStorage token cleared", !store.get("saathi_session"));
ok("canonical AUTH_REQUIRED transition count == 1", enterAuthRequired === 1);
ok("saathi:auth-required event count == 1 (concurrent dedup)", canonicalEvents === 1);
ok("final state AUTH_REQUIRED", A.getAuthSnapshot().state === "AUTH_REQUIRED");

// ── extra stale 401 while already AUTH_REQUIRED → zero new events ──
const evBefore = canonicalEvents, txBefore = enterAuthRequired;
store.set("saathi_session", "stale-again"); // simulate a lingering request that still had a token
await afetch(`${B}/api/v1/missions/x`, { method: "GET" });
ok("stale 401 while AUTH_REQUIRED emits 0 new events", canonicalEvents === evBefore);
ok("stale 401 while AUTH_REQUIRED causes 0 new transitions", enterAuthRequired === txBefore);

// ── Incident 2: re-login, then a genuinely NEW auth-loss → exactly one new event ──
await toAuthenticated();
ok("re-authenticated to AUTHENTICATED", A.getAuthSnapshot().state === "AUTHENTICATED");
const evAfterLogin = canonicalEvents;
authOk = false;
await afetch(`${B}/api/v1/control/attention`, { method: "GET" });
ok("new incident emits exactly ONE new event (per-incident, not global)", canonicalEvents === evAfterLogin + 1);
ok("new incident state AUTH_REQUIRED", A.getAuthSnapshot().state === "AUTH_REQUIRED");

console.log(`\nRESULT ${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
