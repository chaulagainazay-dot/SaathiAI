// Server-side enrichment from the scraped ShareSansar datasets.
//
// Every enrichment here is OPTIONAL and fails soft. The market and floorsheet
// routes were correct before this existed and must stay correct when the browser
// is down, ShareSansar changes a layout, or the host is not allowlisted — an
// enrichment that can take a working page offline is a downgrade, not a feature.
//
// So: on any failure these return null, the caller keeps what it had, and the
// response says which enrichment was applied.

const SELF = process.env.SAATHI_SELF_BASE || "http://127.0.0.1:3000";
const TIMEOUT_MS = 130_000;

/** Forward the caller's identity; the browser endpoint is auth-gated. */
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
 * Broker code → name.
 * Returns null rather than an empty map, so a caller can tell "no names
 * available" from "this broker has no name" — the second is a real answer.
 */
export async function brokerNames(request) {
  const d = await fetchDataset("brokers", request);
  if (!d?.rows?.length) return null;
  const names = new Map();
  for (const b of d.rows) {
    if (typeof b.code === "number" && b.name) names.set(b.code, b.name);
  }
  return names.size ? { names, source: d.source?.id || "sharesansar.com", fetchedAt: d.fetchedAt } : null;
}

/**
 * Symbol → sector. Partial by construction: the source page lists each sector's
 * top movers only, so the coverage figure travels with the map.
 */
export async function sectorMap(request) {
  const d = await fetchDataset("sectors", request);
  if (!d?.map || !d.covered) return null;
  const map = new Map(Object.entries(d.map).map(([sym, v]) => [sym, v.sector]));
  return {
    map,
    covered: d.covered,
    sectors: d.sectors || [],
    coverage: d.coverage || "PARTIAL",
    observedOn: d.observedOn || null,
    source: d.source?.id || "sharesansar.com",
  };
}
