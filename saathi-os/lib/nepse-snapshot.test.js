// Durable reference snapshots — atomicity, integrity, and the restart guarantee.
//
// The scenario these are written against is the observed defect: a process dies,
// a new one starts with no network, and the app must still know all 92 brokers
// rather than falling back to 8 — while never calling that cached data live.

import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, readFile, writeFile, rm, mkdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import {
  writeSnapshot, readSnapshot, buildEnvelope, validateEnvelope, checksumOf,
  containsSecretLike, snapshotDir, SNAPSHOT_ERROR, SNAPSHOT_SCHEMA_VERSION, SNAPSHOT_DATASETS,
} from "./nepse/snapshot.js";
import { directoryState, DIRECTORY_STATE, resolveBroker } from "./nepse/directory.js";

const NOW = 1_800_000_000_000;
const root = () => mkdtemp(path.join(tmpdir(), "saathi-snap-"));

/** 92 brokers, as the verified source returns them. */
const BROKERS = Object.fromEntries(
  Array.from({ length: 92 }, (_, i) => [String(i + 1), `Broker Firm ${i + 1}`]),
);
const META = { source: "sharesansar.com", entries: 92, receivedAt: NOW, validatedAt: NOW };

test("a checksum depends on content, not key order", () => {
  assert.equal(checksumOf({ a: 1, b: 2 }), checksumOf({ b: 2, a: 1 }));
  assert.notEqual(checksumOf({ a: 1 }), checksumOf({ a: 2 }));
});

test("a snapshot round-trips with its provenance intact", async () => {
  const r = await root();
  try {
    const w = await writeSnapshot("brokers", BROKERS, META, { root: r });
    assert.equal(w.ok, true);
    const got = await readSnapshot("brokers", { root: r });
    assert.equal(got.ok, true);
    assert.equal(Object.keys(got.payload).length, 92);
    assert.equal(got.source, "sharesansar.com");
    assert.equal(got.entries, 92);
    assert.equal(got.lastSuccessfulRefresh, NOW);
    assert.equal(got.schemaVersion, SNAPSHOT_SCHEMA_VERSION);
  } finally { await rm(r, { recursive: true, force: true }); }
});

// ── PHASE 12: the restart guarantee ──────────────────────────────────────────

test("RESTART — a fresh process with NO network still sees all 92 brokers, as CACHED not live", async () => {
  const r = await root();
  try {
    // 1-2. A verified enrichment is obtained and persisted.
    await writeSnapshot("brokers", BROKERS, META, { root: r });

    // 3-5. The process ends. A new one starts. No live enrichment is available.
    const restored = await readSnapshot("brokers", { root: r });
    const live = null;

    // 6. The directory is still complete.
    assert.equal(restored.ok, true);
    assert.equal(Object.keys(restored.payload).length, 92, "a restart must not shrink the directory");

    // 7. And it is labelled as cached.
    const state = directoryState({
      live,
      cached: { entries: restored.entries, verifiedAt: restored.lastSuccessfulRefresh, source: restored.source },
      fallback: { entries: 8, source: "built-in" },
      nowMs: NOW + 3_600_000,
    });
    assert.equal(state.state, DIRECTORY_STATE.CACHED_LAST_VERIFIED);
    assert.equal(state.entries, 92);

    // 8. Never live.
    assert.notEqual(state.state, DIRECTORY_STATE.LIVE_ENRICHED);

    // And the identity that used to render as "null" now resolves properly.
    const b = resolveBroker(49, [
      { state: DIRECTORY_STATE.CACHED_LAST_VERIFIED, names: restored.payload, verifiedAt: restored.lastSuccessfulRefresh },
      { state: DIRECTORY_STATE.INCOMPLETE_FALLBACK, names: { 58: "Naasa Securities" } },
    ]);
    assert.equal(b.displayName, "Broker Firm 49");
    assert.equal(b.state, DIRECTORY_STATE.CACHED_LAST_VERIFIED);
  } finally { await rm(r, { recursive: true, force: true }); }
});

// ── PHASE 13: a failed refresh must not erase last-known-good ────────────────

test("FAILED REFRESH — an empty payload never overwrites a good snapshot", async () => {
  const r = await root();
  try {
    await writeSnapshot("brokers", BROKERS, META, { root: r });
    for (const bad of [{}, [], null, undefined]) {
      const w = await writeSnapshot("brokers", bad, META, { root: r });
      assert.equal(w.ok, false, `${JSON.stringify(bad)} must be refused`);
      assert.equal(w.reason, SNAPSHOT_ERROR.EMPTY_PAYLOAD);
    }
    const still = await readSnapshot("brokers", { root: r });
    assert.equal(Object.keys(still.payload).length, 92, "last-known-good must survive every failed refresh");
  } finally { await rm(r, { recursive: true, force: true }); }
});

test("a partial refresh replaces atomically and is readable as a whole", async () => {
  const r = await root();
  try {
    await writeSnapshot("brokers", BROKERS, META, { root: r });
    const partial = { 58: "Naasa Securities", 45: "Imperial Securities" };
    const w = await writeSnapshot("brokers", partial, { ...META, entries: 2, validatedAt: NOW + 1000 }, { root: r });
    assert.equal(w.ok, true);
    const got = await readSnapshot("brokers", { root: r });
    assert.equal(Object.keys(got.payload).length, 2);
    assert.equal(got.checksum, checksumOf(partial), "no torn write");
  } finally { await rm(r, { recursive: true, force: true }); }
});

// ── PHASE 5: corruption ──────────────────────────────────────────────────────

test("a corrupt file is refused, never loaded as trusted", async () => {
  const r = await root();
  try {
    await writeSnapshot("brokers", BROKERS, META, { root: r });
    const f = path.join(snapshotDir(r), "brokers.json");

    await writeFile(f, "{ not json", "utf8");
    assert.equal((await readSnapshot("brokers", { root: r })).reason, SNAPSHOT_ERROR.MALFORMED);

    // Tampered payload, checksum left behind.
    const env = buildEnvelope("brokers", BROKERS, META);
    await writeFile(f, JSON.stringify({ ...env, payload: { 1: "Tampered" } }), "utf8");
    assert.equal((await readSnapshot("brokers", { root: r })).reason, SNAPSHOT_ERROR.CHECKSUM_MISMATCH);

    // A future schema is not read on a guess.
    await writeFile(f, JSON.stringify({ ...env, schemaVersion: 99 }), "utf8");
    const mm = await readSnapshot("brokers", { root: r });
    assert.equal(mm.reason, SNAPSHOT_ERROR.SCHEMA_MISMATCH);
    assert.equal(mm.found, 99);
  } finally { await rm(r, { recursive: true, force: true }); }
});

test("an absent snapshot is ABSENT, distinct from a corrupt one", async () => {
  const r = await root();
  try {
    assert.equal((await readSnapshot("brokers", { root: r })).reason, SNAPSHOT_ERROR.ABSENT);
  } finally { await rm(r, { recursive: true, force: true }); }
});

test("a snapshot written for one dataset is not served as another", async () => {
  const r = await root();
  try {
    await writeSnapshot("brokers", BROKERS, META, { root: r });
    await mkdir(snapshotDir(r), { recursive: true });
    const env = buildEnvelope("brokers", BROKERS, META);
    await writeFile(path.join(snapshotDir(r), "sectors.json"), JSON.stringify(env), "utf8");
    assert.equal((await readSnapshot("sectors", { root: r })).reason, SNAPSHOT_ERROR.MALFORMED);
  } finally { await rm(r, { recursive: true, force: true }); }
});

// ── PHASE 17: no secret may ever be persisted ────────────────────────────────

test("a payload carrying anything credential-shaped is refused before it touches disk", async () => {
  const r = await root();
  try {
    const cases = [
      { cookie: "session=abc123" },
      { headers: { authorization: "Bearer eyJhbGciOi" } },
      { nested: { deep: { apiKey: "sk-live-xxxx" } } },
      { list: [{ "set-cookie": "sid=1" }] },
      { note: "Bearer eyJhbGciOiJIUzI1NiJ9.aaaa" },
      { trace: "sid=deadbeefdeadbeef" },
      { password: "hunter2" },
      { x_saathi_token: "t" , "x-saathi-token": "t" },
    ];
    for (const bad of cases) {
      const w = await writeSnapshot("brokers", bad, META, { root: r });
      assert.equal(w.ok, false, `${JSON.stringify(bad)} must be refused`);
      assert.equal(w.reason, SNAPSHOT_ERROR.SECRET_DETECTED);
    }
    assert.equal((await readSnapshot("brokers", { root: r })).reason, SNAPSHOT_ERROR.ABSENT,
      "a refused write must leave nothing behind");
  } finally { await rm(r, { recursive: true, force: true }); }
});

test("ordinary reference data is not mistaken for a secret", () => {
  assert.equal(containsSecretLike({ 58: "Naasa Securities Co. Ltd." }), false);
  assert.equal(containsSecretLike({ NABIL: "Commercial Bank" }), false);
  assert.equal(containsSecretLike("Imperial Securities"), false);
});

test("only the closed list of datasets may persist", async () => {
  const r = await root();
  try {
    assert.deepEqual([...SNAPSHOT_DATASETS], ["brokers", "sectors"]);
    for (const bad of ["../escape", "secrets", "Brokers", "", null]) {
      assert.equal((await writeSnapshot(bad, BROKERS, META, { root: r })).ok, false);
    }
  } finally { await rm(r, { recursive: true, force: true }); }
});

test("a snapshot file is written owner-only", async () => {
  const r = await root();
  try {
    await writeSnapshot("brokers", BROKERS, META, { root: r });
    const { stat } = await import("node:fs/promises");
    const s = await stat(path.join(snapshotDir(r), "brokers.json"));
    assert.equal(s.mode & 0o077, 0, "reference cache must not be group/world readable");
  } finally { await rm(r, { recursive: true, force: true }); }
});

test("no temp file is left behind after a successful commit", async () => {
  const r = await root();
  try {
    await writeSnapshot("brokers", BROKERS, META, { root: r });
    const { readdir } = await import("node:fs/promises");
    const files = await readdir(snapshotDir(r));
    assert.deepEqual(files, ["brokers.json"]);
  } finally { await rm(r, { recursive: true, force: true }); }
});

test("the envelope validates independently of any disk", () => {
  const env = buildEnvelope("brokers", BROKERS, META);
  assert.equal(validateEnvelope(env, "brokers").ok, true);
  assert.equal(validateEnvelope({ ...env, checksum: "0".repeat(64) }, "brokers").reason, SNAPSHOT_ERROR.CHECKSUM_MISMATCH);
  assert.equal(validateEnvelope(null, "brokers").reason, SNAPSHOT_ERROR.MALFORMED);
});
