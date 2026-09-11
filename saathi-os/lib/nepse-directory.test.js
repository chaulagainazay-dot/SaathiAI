// Reference directory state, authority and identity rendering.
//
// These tests exist because of two observed defects: a restart silently replaced
// 92 verified broker names with 8 built-in ones, and the built-in list rendered
// the literal string "null" beside real money flows while calling broker 45 by a
// different firm's name than the verified source does.

import test from "node:test";
import assert from "node:assert/strict";
import {
  DIRECTORY_STATE, DIRECTORY_STATE_LABEL, DIRECTORY_STATE_SEVERITY, AUTHORITY,
  FRESHNESS, FRESHNESS_POLICY, freshnessOf, describeAge,
  resolveBroker, resolveSector, directoryState, stateBanner,
  unknownBrokerLabel, UNKNOWN_SECTOR,
} from "./nepse/directory.js";
import { INDICATOR_STATUS } from "./nepse/indicators.js";

const NOW = 1_800_000_000_000;
const HOUR = 3_600_000;
const DAY = 24 * HOUR;

const live = (names, verifiedAt = NOW - HOUR) =>
  ({ state: DIRECTORY_STATE.LIVE_ENRICHED, names, verifiedAt, source: "sharesansar.com" });
const cached = (names, verifiedAt = NOW - 2 * DAY) =>
  ({ state: DIRECTORY_STATE.CACHED_LAST_VERIFIED, names, verifiedAt, source: "sharesansar.com" });
const builtin = (names) =>
  ({ state: DIRECTORY_STATE.INCOMPLETE_FALLBACK, names, verifiedAt: null, source: "built-in" });

// ── RULE 4: never a null identity ────────────────────────────────────────────

test("an unknown broker renders a deterministic label, never null", () => {
  const r = resolveBroker(49, [builtin({ 58: "Naasa Securities" })]);
  assert.equal(r.displayName, "Broker 49");
  assert.equal(r.known, false);
  assert.equal(r.state, DIRECTORY_STATE.UNAVAILABLE);
  assert.equal(r.quality, INDICATOR_STATUS.FIELD_UNAVAILABLE);
});

test("every junk name the pipeline can emit is treated as absent", () => {
  for (const junk of [null, undefined, "", "   ", "null", "NULL", "undefined", "None", "NaN", "n/a", "-", "--", 42, {}]) {
    const r = resolveBroker(49, [live({ 49: junk })]);
    assert.equal(r.displayName, "Broker 49", `${JSON.stringify(junk)} must not become a name`);
    assert.equal(r.known, false);
  }
});

test("no resolver output can ever be a forbidden literal", () => {
  const forbidden = /^(null|undefined|none|nan)$/i;
  const cases = [
    resolveBroker(null, []), resolveBroker(0, []), resolveBroker("abc", []),
    resolveBroker(49, [builtin({})]), resolveBroker(58, [live({ 58: "Naasa" })]),
  ];
  for (const c of cases) {
    assert.equal(typeof c.displayName, "string");
    assert.ok(c.displayName.length > 0);
    assert.ok(!forbidden.test(c.displayName), `emitted "${c.displayName}"`);
  }
  assert.equal(resolveBroker(null, []).displayName, "Unknown broker");
});

// ── RULE 5: authority, and conflicts recorded not merged ─────────────────────

test("a verified source outranks the known-bad built-in list", () => {
  // The real case: 45 is Imperial per ShareSansar, "Kumari Securities" in the fallback.
  const r = resolveBroker(45, [
    builtin({ 45: "Kumari Securities" }),
    live({ 45: "Imperial Securities Co. Limited" }),
  ]);
  assert.equal(r.displayName, "Imperial Securities Co. Limited");
  assert.equal(r.state, DIRECTORY_STATE.LIVE_ENRICHED);
});

test("a disagreement is RECORDED, not merged and not dropped", () => {
  const r = resolveBroker(45, [
    builtin({ 45: "Kumari Securities" }),
    live({ 45: "Imperial Securities Co. Limited" }),
  ]);
  assert.equal(r.quality, INDICATOR_STATUS.DATA_CONFLICT);
  assert.equal(r.conflict.chosen, "Imperial Securities Co. Limited");
  assert.deepEqual(r.conflict.rejected, [{ name: "Kumari Securities", from: DIRECTORY_STATE.INCOMPLETE_FALLBACK }]);
});

test("agreement across tiers is not a conflict", () => {
  const r = resolveBroker(58, [builtin({ 58: "Naasa Securities" }), live({ 58: "Naasa Securities" })]);
  assert.equal(r.quality, INDICATOR_STATUS.VALID);
  assert.equal(r.conflict, null);
});

test("cached outranks fallback, and live outranks cached", () => {
  assert.ok(AUTHORITY.LIVE_ENRICHED > AUTHORITY.CACHED_LAST_VERIFIED);
  assert.ok(AUTHORITY.CACHED_LAST_VERIFIED > AUTHORITY.INCOMPLETE_FALLBACK);
  const r = resolveBroker(45, [builtin({ 45: "Kumari Securities" }), cached({ 45: "Imperial Securities" })]);
  assert.equal(r.displayName, "Imperial Securities");
  assert.equal(r.state, DIRECTORY_STATE.CACHED_LAST_VERIFIED);
});

test("a lower tier still answers when the higher tier does not know the code", () => {
  const r = resolveBroker(58, [live({ 45: "Imperial" }), builtin({ 58: "Naasa Securities" })]);
  assert.equal(r.displayName, "Naasa Securities");
  assert.equal(r.state, DIRECTORY_STATE.INCOMPLETE_FALLBACK);
});

// ── Sectors ──────────────────────────────────────────────────────────────────

test("an unknown sector is a dash, never a fabricated classification", () => {
  const r = resolveSector("MYSTERY", [{ state: DIRECTORY_STATE.LIVE_ENRICHED, sectors: { NABIL: "Commercial Bank" } }]);
  assert.equal(r.displaySector, UNKNOWN_SECTOR);
  assert.equal(r.sector, null);
  assert.equal(r.known, false);
});

test("sector resolution is case-insensitive on the symbol and respects authority", () => {
  const r = resolveSector("nabil", [
    { state: DIRECTORY_STATE.INCOMPLETE_FALLBACK, sectors: { NABIL: "Banks" } },
    { state: DIRECTORY_STATE.LIVE_ENRICHED, sectors: { NABIL: "Commercial Bank" }, source: "sharesansar.com" },
  ]);
  assert.equal(r.displaySector, "Commercial Bank");
  assert.equal(r.quality, INDICATOR_STATUS.DATA_CONFLICT);
});

// ── RULE 11 / freshness ──────────────────────────────────────────────────────

test("freshness is classified against a versioned policy", () => {
  assert.equal(FRESHNESS_POLICY.version, 1);
  assert.equal(freshnessOf(NOW - HOUR, NOW), FRESHNESS.FRESH);
  assert.equal(freshnessOf(NOW - 2 * DAY, NOW), FRESHNESS.STALE_BUT_USABLE);
  assert.equal(freshnessOf(NOW - 30 * DAY, NOW), FRESHNESS.EXPIRED);
});

test("an unknown or future timestamp is UNKNOWN, never FRESH", () => {
  assert.equal(freshnessOf(null, NOW), FRESHNESS.UNKNOWN);
  assert.equal(freshnessOf(undefined, NOW), FRESHNESS.UNKNOWN);
  assert.equal(freshnessOf(NOW + DAY, NOW), FRESHNESS.UNKNOWN);
});

test("age reads in human units, and refuses to invent one", () => {
  assert.equal(describeAge(NOW - 30_000, NOW), "just now");
  assert.equal(describeAge(NOW - 5 * 60_000, NOW), "5 minutes ago");
  assert.equal(describeAge(NOW - 3 * HOUR, NOW), "3 hours ago");
  assert.equal(describeAge(NOW - 2 * DAY, NOW), "2 days ago");
  assert.equal(describeAge(null, NOW), null);
});

// ── Directory state selection ────────────────────────────────────────────────

test("a successful live fetch is LIVE_ENRICHED", () => {
  const s = directoryState({ live: { entries: 92, verifiedAt: NOW, source: "sharesansar.com" }, nowMs: NOW });
  assert.equal(s.state, DIRECTORY_STATE.LIVE_ENRICHED);
  assert.equal(s.entries, 92);
});

test("with live unavailable, a good cache is CACHED_LAST_VERIFIED — never live", () => {
  const s = directoryState({
    live: null,
    cached: { entries: 92, verifiedAt: NOW - 2 * DAY, source: "sharesansar.com" },
    fallback: { entries: 8, source: "built-in" },
    nowMs: NOW,
  });
  assert.equal(s.state, DIRECTORY_STATE.CACHED_LAST_VERIFIED);
  assert.equal(s.entries, 92, "the restart must not shrink the directory");
  assert.equal(s.freshness, FRESHNESS.STALE_BUT_USABLE);
});

test("an EXPIRED cache is not used — it falls through to the fallback", () => {
  const s = directoryState({
    cached: { entries: 92, verifiedAt: NOW - 30 * DAY },
    fallback: { entries: 8, source: "built-in" },
    nowMs: NOW,
  });
  assert.equal(s.state, DIRECTORY_STATE.INCOMPLETE_FALLBACK);
});

test("an empty live result does not beat a good cache", () => {
  const s = directoryState({
    live: { entries: 0, verifiedAt: NOW },
    cached: { entries: 92, verifiedAt: NOW - HOUR },
    nowMs: NOW,
  });
  assert.equal(s.state, DIRECTORY_STATE.CACHED_LAST_VERIFIED);
});

test("nothing anywhere is UNAVAILABLE, not an empty fallback pretending to be data", () => {
  const s = directoryState({ nowMs: NOW });
  assert.equal(s.state, DIRECTORY_STATE.UNAVAILABLE);
  assert.equal(s.entries, 0);
});

// ── RULE 3 / RULE 11: visibility and the false-live invariant ────────────────

test("PERMANENT INVARIANT — no state label except the live one may say 'live'", () => {
  for (const [state, label] of Object.entries(DIRECTORY_STATE_LABEL)) {
    if (state === DIRECTORY_STATE.LIVE_ENRICHED) continue;
    assert.ok(!/\blive\b/i.test(label) || /unavailable/i.test(label),
      `${state} label must not read as live: "${label}"`);
  }
  assert.equal(stateBanner(DIRECTORY_STATE.CACHED_LAST_VERIFIED, {}).isLive, false);
  assert.equal(stateBanner(DIRECTORY_STATE.INCOMPLETE_FALLBACK, {}).isLive, false);
  assert.equal(stateBanner(DIRECTORY_STATE.UNAVAILABLE, {}).isLive, false);
  assert.equal(stateBanner(DIRECTORY_STATE.LIVE_ENRICHED, {}).isLive, true);
});

test("fallback is a warning, not a caption", () => {
  assert.equal(DIRECTORY_STATE_SEVERITY.INCOMPLETE_FALLBACK, "warning");
  assert.equal(DIRECTORY_STATE_SEVERITY.UNAVAILABLE, "warning");
  assert.equal(DIRECTORY_STATE_SEVERITY.CACHED_LAST_VERIFIED, "notice");
  assert.equal(DIRECTORY_STATE_SEVERITY.LIVE_ENRICHED, "none");
  const b = stateBanner(DIRECTORY_STATE.INCOMPLETE_FALLBACK, {});
  assert.ok(/limited reference data/i.test(b.label));
});

test("a cached banner carries its age so 'cached' is never open-ended", () => {
  const b = stateBanner(DIRECTORY_STATE.CACHED_LAST_VERIFIED, { verifiedAt: NOW - 3 * HOUR, nowMs: NOW, entries: 92, expected: 92 });
  assert.equal(b.age, "3 hours ago");
  assert.equal(b.severity, "notice");
  assert.ok(b.coverage.includes("92"));
});

test("an unknown state falls to the safest banner rather than throwing", () => {
  const b = stateBanner("SOMETHING_NEW", {});
  assert.equal(b.severity, "warning");
  assert.equal(b.isLive, false);
});
