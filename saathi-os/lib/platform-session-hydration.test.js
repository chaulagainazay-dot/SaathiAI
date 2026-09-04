import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createPlatformSessionHydrator } from "./platform-client.js";

test("platform session hydration persists one exchanged token without returning it", async () => {
  let exchanges = 0;
  const persisted = [];
  const hydrate = createPlatformSessionHydrator({
    readToken: () => "",
    exchange: async () => { exchanges += 1; return { ok: true, token: "platform-secret" }; },
    persist: (token) => persisted.push(token),
  });
  const result = await hydrate();
  assert.deepEqual(result, { ok: true, reused: false });
  assert.equal(exchanges, 1);
  assert.deepEqual(persisted, ["platform-secret"]);
  assert.equal(JSON.stringify(result).includes("platform-secret"), false);
});

test("an existing platform token avoids a redundant exchange", async () => {
  let exchanges = 0;
  const hydrate = createPlatformSessionHydrator({
    readToken: () => "existing-secret",
    exchange: async () => { exchanges += 1; return { ok: true, token: "new-secret" }; },
  });
  assert.deepEqual(await hydrate(), { ok: true, reused: true });
  assert.equal(exchanges, 0);
});

test("concurrent hydration calls share one exchange", async () => {
  let exchanges = 0;
  let release;
  const pending = new Promise((resolve) => { release = resolve; });
  const hydrate = createPlatformSessionHydrator({
    readToken: () => "",
    exchange: async () => { exchanges += 1; await pending; return { ok: true, token: "one-secret" }; },
    persist: () => {},
  });
  const first = hydrate();
  const second = hydrate();
  release();
  assert.deepEqual(await Promise.all([first, second]), [
    { ok: true, reused: false },
    { ok: true, reused: false },
  ]);
  assert.equal(exchanges, 1);
});

test("exchange failure is bounded and retryable without another password", async () => {
  let attempts = 0;
  const hydrate = createPlatformSessionHydrator({
    readToken: () => "",
    exchange: async () => {
      attempts += 1;
      return attempts === 1 ? { ok: false, code: "CANONICAL_SESSION_INVALID" } : { ok: true, token: "retry-secret" };
    },
    persist: () => {},
  });
  assert.deepEqual(await hydrate(), { ok: false, code: "CANONICAL_SESSION_INVALID" });
  assert.deepEqual(await hydrate(), { ok: true, reused: false });
  assert.equal(attempts, 2);
});

test("malformed or empty exchange responses never fabricate a token", async () => {
  for (const response of [{ ok: true }, { ok: true, token: "" }, { ok: true, token: 42 }]) {
    let persisted = false;
    const hydrate = createPlatformSessionHydrator({
      readToken: () => "",
      exchange: async () => response,
      persist: () => { persisted = true; },
    });
    const result = await hydrate();
    assert.equal(result.ok, false);
    assert.equal(persisted, false);
  }
});

test("unlock owns post-login hydration and the dock still requires a token", async () => {
  const page = await readFile(new URL("../app/unlock/page.jsx", import.meta.url), "utf8");
  const dock = await readFile(new URL("../components/voice/VoiceRuntimeDock.jsx", import.meta.url), "utf8");
  const client = await readFile(new URL("./platform-client.js", import.meta.url), "utf8");
  const provider = await readFile(new URL("../components/voice/VoiceRuntimeProvider.jsx", import.meta.url), "utf8");
  assert.match(page, /ensurePlatformSession/);
  assert.match(page, /Retry platform connection/);
  assert.match(client, /PLATFORM_CONTEXT_EVENT/);
  assert.match(provider, /hasSessionToken\(\) && !getToken\(\)/);
  assert.match(provider, /ensurePlatformSession\(\)/);
  assert.match(dock, /if \(!token\) return null/);
});
