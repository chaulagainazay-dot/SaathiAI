// Durable last-known-good reference snapshots. Server-side, Node fs.
//
// WHY THIS EXISTS: a backend restart replaced 92 verified broker names with 8
// built-in ones and 183 mapped sectors with 24, because the good data lived only
// in a process's memory. Nothing was wrong with the data — it simply had nowhere
// to survive.
//
// WHY A FILE AND NOT SQLITE: SQLite is canonical on the Python side, but this
// enrichment is produced and consumed entirely in the Next layer, and saathi-os
// carries no SQLite binding (adding one means better-sqlite3, which already warns
// it does not support this machine's Node). A snapshot is a small document written
// whole, so write-temp-then-rename gives real atomicity with no new dependency.
// It lands in the canonical `.runtime/` directory that saathi/runtime_paths.py owns.
//
// WHAT MAY NEVER BE WRITTEN: cookies, session tokens, authorization headers, API
// secrets, or any authenticated browser state. Snapshots hold normalized PUBLIC
// reference data only, and a guard below refuses anything that smells otherwise.

import { createHash } from "node:crypto";
import { mkdir, readFile, rename, unlink, writeFile } from "node:fs/promises";
import path from "node:path";

export const SNAPSHOT_SCHEMA_VERSION = 1;

export const SNAPSHOT_ERROR = {
  ABSENT: "ABSENT",
  UNREADABLE: "UNREADABLE",
  MALFORMED: "MALFORMED",
  SCHEMA_MISMATCH: "SCHEMA_MISMATCH",
  CHECKSUM_MISMATCH: "CHECKSUM_MISMATCH",
  EMPTY_PAYLOAD: "EMPTY_PAYLOAD",
  SECRET_DETECTED: "SECRET_DETECTED",
};

/** Datasets allowed to persist. A closed list — not "whatever a caller passes". */
export const SNAPSHOT_DATASETS = Object.freeze(["brokers", "sectors"]);

const DATASET_RE = /^[a-z][a-z0-9_-]{0,31}$/;

/**
 * Keys that must never appear in a persisted payload. Checked on WRITE, so a
 * mistake fails at the point it is made rather than lying on disk until someone
 * reads it.
 */
const SECRET_KEY_RE = /(cookie|authorization|auth[_-]?token|bearer|session[_-]?id|api[_-]?key|secret|password|passwd|credential|set-cookie|x-saathi-token)/i;

export function containsSecretLike(value, depth = 0) {
  if (depth > 8 || value === null || value === undefined) return false;
  if (Array.isArray(value)) return value.some((v) => containsSecretLike(v, depth + 1));
  if (typeof value === "object") {
    for (const [k, v] of Object.entries(value)) {
      if (SECRET_KEY_RE.test(k)) return true;
      if (containsSecretLike(v, depth + 1)) return true;
    }
    return false;
  }
  if (typeof value === "string") {
    // A bearer token or a Set-Cookie line pasted into a value, not just a key.
    if (/^Bearer\s+\S{8,}/i.test(value)) return true;
    if (/(^|;\s*)(session|sid|token)=/i.test(value)) return true;
  }
  return false;
}

/** Canonical directory, honouring the same env the Python side honours. */
export function snapshotDir(root = null) {
  const base = root
    || process.env.SAATHI_RUNTIME_STATE_DIR
    || path.join(process.cwd(), "..", ".runtime");
  return path.join(base, "nepse-directory");
}

const fileFor = (dataset, root) => path.join(snapshotDir(root), `${dataset}.json`);

/** Stable stringify so a checksum depends on content, not key order. */
function canonical(value) {
  if (value === null || typeof value !== "object") return JSON.stringify(value) ?? "null";
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  const keys = Object.keys(value).sort();
  return `{${keys.map((k) => `${JSON.stringify(k)}:${canonical(value[k])}`).join(",")}}`;
}

export function checksumOf(payload) {
  return createHash("sha256").update(canonical(payload)).digest("hex");
}

/**
 * Build the envelope. Pure — separated from the write so the shape is testable
 * without touching a disk.
 */
export function buildEnvelope(dataset, payload, { source, entries, receivedAt, validatedAt } = {}) {
  return {
    schemaVersion: SNAPSHOT_SCHEMA_VERSION,
    dataset,
    source: source ?? null,
    entries: Number.isFinite(entries) ? entries : null,
    receivedAt: receivedAt ?? null,
    validatedAt: validatedAt ?? null,
    lastSuccessfulRefresh: validatedAt ?? receivedAt ?? null,
    checksum: checksumOf(payload),
    payload,
  };
}

/** Everything a reader must confirm before trusting a file. */
export function validateEnvelope(env, dataset) {
  if (!env || typeof env !== "object") return { ok: false, reason: SNAPSHOT_ERROR.MALFORMED };
  if (env.schemaVersion !== SNAPSHOT_SCHEMA_VERSION) {
    return { ok: false, reason: SNAPSHOT_ERROR.SCHEMA_MISMATCH, found: env.schemaVersion ?? null };
  }
  if (dataset && env.dataset !== dataset) return { ok: false, reason: SNAPSHOT_ERROR.MALFORMED };
  const p = env.payload;
  const empty = p === null || p === undefined
    || (Array.isArray(p) && p.length === 0)
    || (typeof p === "object" && !Array.isArray(p) && Object.keys(p).length === 0);
  if (empty) return { ok: false, reason: SNAPSHOT_ERROR.EMPTY_PAYLOAD };
  if (typeof env.checksum !== "string" || env.checksum !== checksumOf(p)) {
    return { ok: false, reason: SNAPSHOT_ERROR.CHECKSUM_MISMATCH };
  }
  return { ok: true };
}

/**
 * Commit a snapshot atomically.
 * Written to a temp file in the same directory and renamed over the target, so a
 * crash mid-write leaves the previous good file untouched rather than a truncated
 * one. A rejected payload never reaches the disk at all.
 */
export async function writeSnapshot(dataset, payload, meta = {}, { root = null } = {}) {
  if (!DATASET_RE.test(String(dataset || ""))) return { ok: false, reason: SNAPSHOT_ERROR.MALFORMED };
  if (!SNAPSHOT_DATASETS.includes(dataset)) return { ok: false, reason: SNAPSHOT_ERROR.MALFORMED };
  if (containsSecretLike(payload) || containsSecretLike(meta.source)) {
    return { ok: false, reason: SNAPSHOT_ERROR.SECRET_DETECTED };
  }
  const env = buildEnvelope(dataset, payload, meta);
  const check = validateEnvelope(env, dataset);
  // An empty refresh must never overwrite a good file — that is the whole point.
  if (!check.ok) return { ok: false, reason: check.reason };

  const dir = snapshotDir(root);
  const target = fileFor(dataset, root);
  const tmp = `${target}.${process.pid}.tmp`;
  try {
    await mkdir(dir, { recursive: true });
    await writeFile(tmp, JSON.stringify(env), { encoding: "utf8", mode: 0o600 });
    await rename(tmp, target);
    return { ok: true, path: target, checksum: env.checksum, entries: env.entries };
  } catch (e) {
    await unlink(tmp).catch(() => {});
    return { ok: false, reason: SNAPSHOT_ERROR.UNREADABLE, detail: String(e?.message || e).slice(0, 200) };
  }
}

/**
 * Read a snapshot, refusing anything that fails integrity.
 * A corrupt file is reported, never returned as trusted data — the caller then
 * degrades visibly instead of rendering nonsense with a confident label.
 */
export async function readSnapshot(dataset, { root = null } = {}) {
  if (!SNAPSHOT_DATASETS.includes(dataset)) return { ok: false, reason: SNAPSHOT_ERROR.MALFORMED };
  let text;
  try {
    text = await readFile(fileFor(dataset, root), "utf8");
  } catch (e) {
    return { ok: false, reason: e?.code === "ENOENT" ? SNAPSHOT_ERROR.ABSENT : SNAPSHOT_ERROR.UNREADABLE };
  }
  let env;
  try { env = JSON.parse(text); } catch { return { ok: false, reason: SNAPSHOT_ERROR.MALFORMED }; }
  const check = validateEnvelope(env, dataset);
  if (!check.ok) return { ok: false, reason: check.reason, found: check.found ?? null };
  return {
    ok: true,
    dataset,
    payload: env.payload,
    source: env.source,
    entries: env.entries,
    receivedAt: env.receivedAt,
    validatedAt: env.validatedAt,
    lastSuccessfulRefresh: env.lastSuccessfulRefresh,
    checksum: env.checksum,
    schemaVersion: env.schemaVersion,
  };
}
