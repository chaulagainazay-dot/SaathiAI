// One SaathiOS application backend.
//
// The UI used to read all of its data from an Oracle VM while the Next server
// used :8765 for governed-browser and NEPSE work — two SaathiOS application
// backends behind one product. These tests pin the properties that keep that
// from coming back silently.

import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "..");
const apiSrc = readFileSync(path.join(HERE, "nepse/../api.js"), "utf8");
const startSh = readFileSync(path.resolve(ROOT, "../scripts/start_local.sh"), "utf8");

const VM_HOST = "140-245-193-190";

test("the startup script points the UI at the local canonical backend", () => {
  const line = startSh.split("\n").find((l) => l.includes("NEXT_PUBLIC_SAATHI_API="));
  assert.ok(line, "start_local.sh must set NEXT_PUBLIC_SAATHI_API");
  assert.ok(/127\.0\.0\.1:8765|localhost:8765/.test(line),
    `the default data plane must be local, got: ${line.trim()}`);
  assert.ok(!line.includes(VM_HOST),
    "the VM must not be the default application backend");
});

test("SAATHI_OS_DATA remains the single override lever", () => {
  // Reversing this milestone must stay a one-variable change, not a code edit.
  assert.ok(startSh.includes("${SAATHI_OS_DATA:-"),
    "SAATHI_OS_DATA must still override the data plane");
});

test("no second application backend is hardcoded in the API client", () => {
  assert.ok(!apiSrc.includes(VM_HOST), "the VM host must not appear in lib/api.js");
  assert.ok(!/nip\.io/.test(apiSrc), "no nip.io host may be baked into the client");
});

test("an unset base resolves to the local backend, never a remote one", () => {
  // The `||` bug this comment records: an empty string must not fall through to
  // a remote default. Absence resolves local; an explicit value is honoured.
  const m = apiSrc.match(/export const API_BASE = ([^;]+);/);
  assert.ok(m, "API_BASE must be a single resolved constant");
  assert.ok(/8765/.test(m[1]), "the fallback base must be the local backend");
  assert.ok(!/nip\.io|140-245/.test(m[1]));
});

test("there is exactly one application base, so a missing route cannot silently retarget", () => {
  // No alternate-base retry anywhere: a route the local backend lacks must fail
  // visibly rather than being served by a second backend.
  const bases = [...apiSrc.matchAll(/\$\{(API_BASE|LOCAL_BASE)\}/g)].map((x) => x[1]);
  assert.ok(bases.length > 0);
  assert.deepEqual([...new Set(bases)].sort(), ["API_BASE", "LOCAL_BASE"]);
  // LOCAL_BASE exists only for Mac-only capabilities, and defaults TO API_BASE.
  assert.ok(apiSrc.includes("LOCAL_BASE = (_LOCAL === undefined || _LOCAL === null) ? API_BASE"));
});

test("Mac-only capabilities keep their own base", () => {
  // A remote data plane must never be able to capture the microphone: voice and
  // code-memory stay pinned to the local machine even if API_BASE moves.
  for (const p of ["/api/v1/voice/command", "/api/v1/voice/enroll", "/api/v1/code-memory/status"]) {
    const re = new RegExp(`\\$\\{LOCAL_BASE\\}${p.replace(/\//g, "\\/")}`);
    assert.ok(re.test(apiSrc), `${p} must be called on LOCAL_BASE`);
  }
});

test("the platform client inherits the one application base", () => {
  const plat = readFileSync(path.join(ROOT, "lib/platform-client.js"), "utf8");
  assert.ok(plat.includes('import { API_BASE }'),
    "Central Command / Trading Ops must use the same base as everything else");
  assert.ok(!plat.includes(VM_HOST));
});
