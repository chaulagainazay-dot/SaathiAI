// Cookie-auth browser contract: afetch relies on the first-party HttpOnly
// cookie (credentials:"include") and never reads/injects a bearer. Browser JS
// has no readable session credential.
import { test } from "node:test";
import assert from "node:assert";

// minimal browser globals for importing the module
globalThis.localStorage = globalThis.localStorage || {
  _m: new Map(),
  getItem(k){ return this._m.has(k) ? this._m.get(k) : null; },
  setItem(k,v){ this._m.set(k, String(v)); },
  removeItem(k){ this._m.delete(k); },
};

const api = await import("../lib/api.js");

test("afetch sends no x-baadar-session header and uses credentials:include", async () => {
  let seen = null;
  globalThis.fetch = async (url, opts) => { seen = opts; return { status: 200, ok: true, json: async () => ({}) }; };
  await api.afetch("/api/v1/control/attention");
  const hdrs = seen.headers || {};
  assert.ok(!("x-baadar-session" in hdrs), "browser afetch must NOT inject x-baadar-session");
  assert.equal(seen.credentials, "include", "afetch must send credentials (cookie)");
});

test("hasSessionToken is false — browser JS cannot read the HttpOnly cookie", () => {
  assert.equal(api.hasSessionToken(), false);
});

test("setSessionToken does not persist a bearer (legacy no-op)", () => {
  api.setSessionToken("should-not-store");
  assert.equal(localStorage.getItem("saathi_session"), null,
    "no localStorage bearer may be written");
});

test("afetch on 401 clears any legacy localStorage bearer", async () => {
  localStorage.setItem("saathi_session", "legacy-leftover");
  globalThis.fetch = async () => ({ status: 401, ok: false, json: async () => ({}) });
  await api.afetch("/api/v1/control/attention");
  assert.equal(localStorage.getItem("saathi_session"), null,
    "legacy bearer must be purged on 401");
});
