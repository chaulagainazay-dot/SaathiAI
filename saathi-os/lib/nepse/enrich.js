// Reference directories with durable state — server side.
//
// The shape of every function here follows one rule learned from a real defect:
// a restart, a timeout, or a dropped session must never turn verified data into
// materially worse data without saying so. So each directory is resolved in tiers:
//
//   live fetch  → persist it, report LIVE_ENRICHED
//   live failed → restore last-known-good, report CACHED_LAST_VERIFIED
//   no cache    → built-in list, report INCOMPLETE_FALLBACK (a warning, not a caption)
//   nothing     → UNAVAILABLE
//
// The enrichment stays OPTIONAL: every caller worked before this existed and must
// keep working when all of it fails.

import { readSnapshot, writeSnapshot } from "./snapshot.js";
import { directoryState, DIRECTORY_STATE } from "./directory.js";
import { BROKERS } from "./data.js";

const SELF = process.env.SAATHI_SELF_BASE || "http://127.0.0.1:3000";
const TIMEOUT_MS = 130_000;

/**
 * The built-in list, kept only as a last resort. It is INCOMPLETE (8 of ~92) and
 * KNOWN TO CONTAIN ERRORS — it calls broker 45 "Kumari Securities" where the
 * verified public source says Imperial Securities. It is never authority.
 */
export const FALLBACK_BROKER_NAMES = Object.freeze(
  Object.fromEntries(BROKERS.map((b) => [String(b.code), b.name])),
);

function authHeaders(request) {
  const h = { accept: "application/json" };
  const cookie = request?.headers?.get?.("cookie");
  const bearer = request?.headers?.get?.("authorization");
  if (cookie) h.cookie = cookie;
  if (bearer) h.authorization = bearer;
  return h;
}

async function fetchDataset(dataset, request) {
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), TIMEOUT_MS);
  try {
    const base = request?.nextUrl?.origin || SELF;
    const res = await fetch(`${base}/api/nepse/sharesansar?dataset=${dataset}`, {
      headers: authHeaders(request), signal: ac.signal, cache: "no-store",
    });
    if (!res.ok) return null;
    const json = await res.json();
    return json?.available ? json : null;
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Resolve one directory through the tiers.
 * `extract` turns a live payload into a plain object of entries, or null if the
 * payload is unusable — a live response that yields nothing must not be persisted
 * and must not beat a good cache.
 */
async function resolveDirectory({ dataset, request, extract, fallback, nowMs }) {
  const now = Number.isFinite(nowMs) ? nowMs : Date.now();

  const liveRaw = await fetchDataset(dataset, request);
  const liveEntries = liveRaw ? extract(liveRaw) : null;
  if (liveEntries && Object.keys(liveEntries).length) {
    const meta = {
      source: liveRaw.source?.id || liveRaw.source || "sharesansar.com",
      entries: Object.keys(liveEntries).length,
      receivedAt: now,
      validatedAt: now,
    };
    // Persist BEFORE returning, so the next restart inherits this. A failed write
    // is not fatal — the live answer is still correct for this request.
    await writeSnapshot(dataset, liveEntries, meta).catch(() => {});
    const st = directoryState({
      live: { entries: meta.entries, verifiedAt: now, source: meta.source }, nowMs: now,
    });
    // NB: directoryState returns `entries` as a COUNT. Spreading it over the
    // entry MAP replaced the data with a number and emptied the directory — the
    // name is deliberately different now.
    return { records: liveEntries, ...st, cacheReason: null };
  }

  const snap = await readSnapshot(dataset).catch(() => null);
  if (snap?.ok && snap.payload && Object.keys(snap.payload).length) {
    const st = directoryState({
      live: null,
      cached: { entries: snap.entries ?? Object.keys(snap.payload).length,
                verifiedAt: snap.lastSuccessfulRefresh, source: snap.source },
      fallback: fallback ? { entries: Object.keys(fallback).length, source: "built-in" } : null,
      nowMs: now,
    });
    // An EXPIRED cache falls through to the fallback rather than being served.
    if (st.state === DIRECTORY_STATE.CACHED_LAST_VERIFIED) {
      return { records: snap.payload, ...st, cacheReason: null };
    }
  }

  const st = directoryState({
    live: null, cached: null,
    fallback: fallback ? { entries: Object.keys(fallback).length, source: "built-in" } : null,
    nowMs: now,
  });
  return {
    records: st.state === DIRECTORY_STATE.INCOMPLETE_FALLBACK ? fallback : null,
    ...st,
    cacheReason: snap && !snap.ok ? snap.reason : "NO_CACHE",
  };
}

/** Broker code → name, with state. Codes absent here render as "Broker N". */
export async function brokerDirectory(request, { nowMs = null } = {}) {
  const d = await resolveDirectory({
    dataset: "brokers",
    request,
    nowMs,
    fallback: FALLBACK_BROKER_NAMES,
    extract: (payload) => {
      const out = {};
      for (const b of payload.rows || []) {
        if (typeof b?.code === "number" && typeof b?.name === "string" && b.name.trim()) {
          out[String(b.code)] = b.name.trim();
        }
      }
      return out;
    },
  });
  const names = new Map(Object.entries(d.records || {}).map(([k, v]) => [Number(k), v]));
  return { ...d, names };
}

/** Symbol → sector, with state. Symbols absent here render as an em dash. */
export async function sectorDirectory(request, { nowMs = null } = {}) {
  const d = await resolveDirectory({
    dataset: "sectors",
    request,
    nowMs,
    // There is no built-in sector map worth the name — the 24-symbol curated list
    // lives in STOCKS and is applied by the caller as a last resort, so an absent
    // cache reports UNAVAILABLE here rather than pretending to be a directory.
    fallback: null,
    extract: (payload) => {
      const out = {};
      for (const [sym, v] of Object.entries(payload.map || {})) {
        const sector = typeof v === "string" ? v : v?.sector;
        if (typeof sector === "string" && sector.trim()) out[sym.toUpperCase()] = sector.trim();
      }
      return out;
    },
  });
  return { ...d, sectors: new Map(Object.entries(d.records || {})) };
}
