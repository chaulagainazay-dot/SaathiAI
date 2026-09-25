// SaathiOS Browser — request shaping and result handling. PURE.
//
// Page text fetched by a browser is the least trustworthy input this app handles:
// written by strangers, and it lands in a UI and, potentially, in a prompt. Two
// rules follow, and they are enforced here rather than in the component:
//
//   1. Content is FENCED before it is rendered or passed on. Steering phrases are
//      neutralized, and the fact that something tried is surfaced rather than
//      quietly cleaned away.
//   2. A refusal is an ANSWER. The governed browser denies by policy far more
//      often than it fails, and "error" tells the reader nothing. Every known
//      denial is mapped to a sentence saying which rule refused and why.

import { fenceUntrusted } from "../news/feed.js";

/** Actions this surface may ask for. Reading a page is not acting on one. */
export const READ_ACTIONS = Object.freeze(["read", "extract", "navigate", "screenshot"]);

/** Actions that change a page. Named so the refusal can be specific, not generic. */
export const WRITE_ACTIONS = Object.freeze(["click", "type", "fill", "submit", "download", "upload"]);

export const MAX_URL_LENGTH = 2000;

/**
 * Validate a URL before it leaves the browser.
 * The server re-checks everything; this exists so a user gets an immediate,
 * specific reason instead of a round trip.
 */
export function validateUrl(input) {
  const raw = String(input || "").trim();
  if (!raw) return { ok: false, reason: "EMPTY", message: "Enter a URL." };
  if (raw.length > MAX_URL_LENGTH) {
    return { ok: false, reason: "TOO_LONG", message: "That URL is too long." };
  }
  // Check the scheme on the RAW input. Schemes like `javascript:` and `data:`
  // carry no "//", so prefixing https:// first would turn a dangerous scheme into
  // an unparseable string and report the wrong reason for the refusal.
  const scheme = raw.match(/^([a-z][a-z0-9+.-]*):/i)?.[1]?.toLowerCase();
  if (scheme && scheme !== "https" && scheme !== "http") {
    return {
      ok: false, reason: "BAD_SCHEME",
      message: `${scheme}: is not fetchable. Use https.`,
    };
  }
  let u;
  try {
    u = new URL(scheme ? raw : `https://${raw}`);
  } catch {
    return { ok: false, reason: "UNPARSEABLE", message: "That is not a URL." };
  }
  if (u.protocol !== "https:" && u.protocol !== "http:") {
    return {
      ok: false, reason: "BAD_SCHEME",
      message: `${u.protocol} is not fetchable. Use https.`,
    };
  }
  // Credentials in a URL get logged, cached and shoulder-surfed. Never send one.
  if (u.username || u.password) {
    return {
      ok: false, reason: "CREDENTIALS_IN_URL",
      message: "That URL carries a username or password. Remove them.",
    };
  }
  return { ok: true, url: u.toString(), host: u.hostname.toLowerCase() };
}

/** Whether an action is one this surface will send at all. */
export function checkAction(action) {
  const a = String(action || "").trim().toLowerCase();
  if (READ_ACTIONS.includes(a)) return { ok: true, action: a };
  if (WRITE_ACTIONS.includes(a)) {
    return {
      ok: false, reason: "WRITE_ACTION",
      message: `"${a}" would change the page. This surface only reads.`,
    };
  }
  return { ok: false, reason: "UNKNOWN_ACTION", message: `Unknown action "${a}".` };
}

/**
 * Turn a governance failure category into something a person can act on.
 * The unknown case deliberately keeps the raw category rather than inventing a
 * friendlier explanation for a rule we cannot name.
 */
export function explainDenial(category, { url = "" } = {}) {
  const host = (() => { try { return new URL(url).hostname; } catch { return url; } })();
  const known = {
    domain_denylisted: {
      title: "Permanently blocked",
      body: `${host} is on the deny list. NEPSE's own portal, the CDSC depository and broker trading systems are authenticated or bot-protected surfaces. They stay blocked whatever the allowlist says.`,
      fixable: false,
    },
    domain: {
      title: "Blocked by domain policy",
      body: `${host} was refused by domain policy.`,
      fixable: false,
    },
    domain_not_allowlisted: {
      title: "Not on the allowlist",
      body: `${host} is not allowed yet. The browser is deny-by-default: a host has to be added deliberately before it can be read.`,
      fixable: true,
    },
    dangerous_or_unsupported_scheme: {
      title: "Scheme refused",
      body: "Only https is fetchable. file:, data: and custom schemes are refused.",
      fixable: false,
    },
    private_network: {
      title: "Private address refused",
      body: "That address is on a private or loopback network. Fetching it would turn this app into a way to reach machines behind the firewall.",
      fixable: false,
    },
    missing_actor: {
      title: "No actor",
      body: "The request carried no actor, so it could not be attributed. Refused.",
      fixable: false,
    },
    BACKEND_401: {
      title: "Sign in first",
      body: "The governed browser is behind authentication on purpose: an endpoint that fetches arbitrary URLs server-side is a request-forgery proxy if anyone can call it. Sign in to SaathiOS and try again.",
      fixable: true,
    },
    BACKEND_UNREACHABLE: {
      title: "Browser not running",
      body: "The SaathiAI backend is not answering, so nothing was fetched.",
      fixable: true,
    },
    TIMEOUT: { title: "Timed out", body: "The page did not come back in time.", fixable: true },
    timeout: { title: "Timed out", body: "The page did not respond in time.", fixable: true },
    fetch_failed: { title: "Could not load", body: "The page did not load.", fixable: true },
  };
  const hit = known[String(category || "").trim()];
  if (hit) return { ...hit, category };
  return {
    title: "Refused",
    body: `The governed browser refused this request${category ? ` (${category})` : ""}.`,
    fixable: false,
    category: category || "",
  };
}

/** Collapse whitespace so a rendered page reads as text rather than a column of gaps. */
export function tidyText(input) {
  return String(input || "")
    .replace(/\r/g, "")
    .replace(/[ \t]+/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .split("\n")
    .map((l) => l.trim())
    .join("\n")
    .trim();
}

/**
 * Split page text into lines that look tabular.
 * Deliberately conservative: it reports CANDIDATES for a table, and never claims
 * to have parsed one. Guessing structure out of flattened text and presenting it
 * as data is how a wrong number gets a confident-looking cell.
 */
export function tabularCandidates(text, { minCells = 3, limit = 200 } = {}) {
  const rows = [];
  // Deliberately NOT tidyText: run-lengths of whitespace ARE the column
  // delimiter, and collapsing them first would erase the only structure present.
  for (const line of String(text || "").replace(/\r/g, "").split("\n")) {
    const cells = line.split(/\s{2,}|\t|\s*\|\s*/).map((c) => c.trim()).filter(Boolean);
    if (cells.length >= minCells) rows.push(cells);
    if (rows.length >= limit) break;
  }
  return rows;
}

/**
 * Normalize a backend response into what the UI renders.
 * Content is fenced here — no caller gets the raw text by accident.
 */
export function normalizeResult(payload, { url = "" } = {}) {
  if (!payload || typeof payload !== "object") {
    return { ok: false, denial: explainDenial("", { url }), content: "", injection: null };
  }
  if (!payload.ok) {
    return {
      ok: false,
      // The backend names it `failure_category`; this app's own route names it
      // `reason`. Read both, or a denial from one of them renders as "Refused".
      denial: explainDenial(payload.failure_category || payload.reason || payload.error, { url }),
      executionId: payload.execution_id || "",
      governed: payload.governed !== false,
      content: "",
      injection: null,
    };
  }
  const fenced = fenceUntrusted(payload.content || "");
  const hits = Array.isArray(payload.injection_hits) ? payload.injection_hits : [];
  return {
    ok: true,
    governed: payload.governed !== false,
    executionId: payload.execution_id || "",
    url: payload.url || url,
    finalOrigin: payload.final_origin || "",
    title: payload.page_title || "",
    action: payload.action || "read",
    truncated: Boolean(payload.truncated),
    content: tidyText(fenced.text),
    // Two independent detectors: the backend's, and this app's own fencing pass.
    injection: hits.length || fenced.flagged
      ? { hits, fencedHere: fenced.flagged }
      : null,
    trust: payload.trust || "UNTRUSTED_EXTERNAL_CONTENT",
    summary: payload.summary || "",
  };
}
