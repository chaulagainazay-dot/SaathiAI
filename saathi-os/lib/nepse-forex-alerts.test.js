import test from "node:test";
import assert from "node:assert/strict";

import {
  BULLION_STATE, FOREX_STATE, NRB_HOST, buildRatesUrl, bullionRates,
  convert, findRate, isAllowedForexUrl, parseNrbRates,
} from "./nepse/forex.js";
import {
  CHANNEL, DELIVERY, advance, channelAvailability, composeNotification, decide,
} from "./alerts/delivery.js";

const payload = (rates, date = "2026-09-07") => ({
  data: { payload: [{ date, published_on: `${date} 00:00:06`, rates }] },
});
const USD = { currency: { iso3: "USD", name: "U.S. Dollar", unit: 1 }, buy: "150.88", sell: "151.48" };
const INR = { currency: { iso3: "INR", name: "Indian Rupee", unit: 100 }, buy: "160.00", sell: "160.15" };

// ══ forex ══════════════════════════════════════════════════════════════════
test("only NRB's own host over HTTPS is allowed", () => {
  assert.equal(isAllowedForexUrl(buildRatesUrl()), true);
  for (const bad of ["http://www.nrb.org.np/api", "https://evil.com/api",
                     "https://nrb.org.np.evil.com/", "not a url", ""]) {
    assert.equal(isAllowedForexUrl(bad), false, bad);
  }
});

test("the rates URL carries the parameters the API requires", () => {
  // page, from and to are all required; omitting any returns 400 with
  // data.payload null. This was a real defect found by probing the live API.
  const u = buildRatesUrl({ date: "2026-09-07" });
  assert.match(u, /[?&]page=1/);
  assert.match(u, /[?&]from=2026-09-07/);
  assert.match(u, /[?&]to=2026-09-07/);
  assert.ok(u.startsWith(`https://${NRB_HOST}/`));
});

test("unit-scaled currencies are normalised per unit", () => {
  // NRB quotes INR per 100 and JPY per 10. Reading those as per-1 would make
  // the Indian rupee look a hundred times too expensive.
  const out = parseNrbRates(payload([USD, INR]));
  assert.equal(out.state, FOREX_STATE.OK);
  assert.equal(findRate(out.rates, "INR").buyPerUnit, 1.6);
  assert.equal(findRate(out.rates, "USD").buyPerUnit, 150.88);
});

test("buy and sell are both carried and neither is defaulted", () => {
  // They differ by ~0.4%; showing one labelled "rate" gets a remittance wrong.
  const r = findRate(parseNrbRates(payload([USD])).rates, "USD");
  assert.equal(r.buy, 150.88);
  assert.equal(r.sell, 151.48);
  assert.ok(r.sell > r.buy);
  assert.ok(r.spreadPct > 0 && r.spreadPct < 1);
});

test("a one-sided rate is rejected rather than shown", () => {
  const out = parseNrbRates(payload([{ currency: { iso3: "BAD", unit: 1 }, buy: "1" }]));
  assert.equal(out.rates.length, 0);
  assert.equal(out.rejected[0].reason, "INCOMPLETE_ROW");
});

test("an unexpected payload shape is MALFORMED, not partially salvaged", () => {
  // Half a currency table read as a whole one is worse than an honest failure.
  assert.equal(parseNrbRates({}).state, FOREX_STATE.MALFORMED);
  assert.equal(parseNrbRates({ data: { payload: null } }).state, FOREX_STATE.MALFORMED);
  assert.equal(parseNrbRates({ data: { payload: [{ date: "x" }] } }).state, FOREX_STATE.MALFORMED);
});

test("a day with no published rates is EMPTY, not an error", () => {
  assert.equal(parseNrbRates({ data: { payload: [] } }).state, FOREX_STATE.EMPTY);
});

test("conversion uses the side that matches the direction of trade", () => {
  const inr = findRate(parseNrbRates(payload([INR])).rates, "INR");
  assert.equal(convert(10_000, inr, { side: "buy" }), 16_000);
  assert.ok(convert(10_000, inr, { side: "sell" }) > 16_000);
  assert.equal(convert(null, inr), null);
  assert.equal(convert(100, null), null);
});

test("bullion reports no source rather than inventing a price", () => {
  // FENEGOSIDA publishes gold; NRB does not. A spot price plus an assumed
  // premium would be fabrication.
  const b = bullionRates();
  assert.equal(b.state, BULLION_STATE.NO_SOURCE);
  assert.deepEqual(b.rates, []);
  assert.match(b.detail, /FENEGOSIDA/);
});

// ══ alert delivery ═════════════════════════════════════════════════════════
const FIRED = { fired: true, value: 520 };
const T0 = 1_000_000_000_000;

test("a first firing is delivered", () => {
  assert.equal(decide(FIRED, {}, { now: T0 }).reason, DELIVERY.SEND);
});

test("an alert already firing does not notify again", () => {
  // The hard part is not firing, it is not RE-firing: a price oscillating
  // around a threshold otherwise sends forty notifications in an hour.
  let h = advance({}, decide(FIRED, {}, { now: T0 }), { now: T0 });
  assert.equal(decide(FIRED, h, { now: T0 + 60_000 }).reason, DELIVERY.SUPPRESSED_UNCHANGED);
});

test("falling back below the threshold re-arms the alert", () => {
  // Without re-arming, a rule fires once and never again.
  let h = advance({}, decide(FIRED, {}, { now: T0 }), { now: T0 });
  h = advance(h, decide({ fired: false }, h, { now: T0 + 1000 }), { now: T0 + 1000 });
  assert.equal(h.lastState, "IDLE");
  const d = decide(FIRED, h, { now: T0 + 20 * 60_000 });
  assert.equal(d.reason, DELIVERY.SEND);
});

test("a cooldown suppresses re-firing and says how long is left", () => {
  let h = advance({}, decide(FIRED, {}, { now: T0 }), { now: T0 });
  h = advance(h, decide({ fired: false }, h, { now: T0 + 1000 }), { now: T0 + 1000 });
  const d = decide(FIRED, h, { now: T0 + 60_000 });
  assert.equal(d.reason, DELIVERY.SUPPRESSED_COOLDOWN);
  assert.ok(d.retryAfterMs > 0);
});

test("an hourly cap stops a flood", () => {
  const sent = Array.from({ length: 12 }, (_, i) => T0 - i * 1000);
  const d = decide(FIRED, { sentTimestamps: sent, lastState: "IDLE" },
                   { now: T0, cooldownMs: 0 });
  assert.equal(d.reason, DELIVERY.SUPPRESSED_RATE_LIMIT);
  assert.equal(d.sentLastHour, 12);
});

test("timestamps older than an hour do not count toward the cap", () => {
  const old = Array.from({ length: 20 }, (_, i) => T0 - 3_600_001 - i * 1000);
  assert.equal(decide(FIRED, { sentTimestamps: old, lastState: "IDLE" },
                      { now: T0, cooldownMs: 0 }).reason, DELIVERY.SEND);
});

test("muting and missing permission are distinct, reported reasons", () => {
  assert.equal(decide(FIRED, {}, { muted: true }).reason, DELIVERY.SUPPRESSED_MUTED);
  // A user who never granted permission should be told their alerts are not
  // reaching them, not left in silence.
  assert.equal(
    decide(FIRED, {}, { channel: CHANNEL.BROWSER_NOTIFICATION, channelAvailable: false }).reason,
    DELIVERY.CHANNEL_UNAVAILABLE,
  );
});

test("not firing is nothing to say, not a suppression", () => {
  const d = decide({ fired: false }, {});
  assert.equal(d.deliver, false);
  assert.equal(d.reason, null);
  assert.equal(d.state, "IDLE");
});

test("every suppression carries a reason so silence can be explained", () => {
  for (const opts of [{ muted: true },
                      { channel: CHANNEL.BROWSER_NOTIFICATION, channelAvailable: false }]) {
    const d = decide(FIRED, {}, opts);
    assert.equal(d.deliver, false);
    assert.ok(d.reason);
  }
});

test("notification text is deterministic, never model-generated", () => {
  const n = composeNotification({ symbol: "NABIL", value: 500, kind: "price_above", id: "r1" }, FIRED);
  assert.equal(n.title, "NABIL reached 500");
  assert.match(n.body, /520/);
  assert.equal(n.tag, "saathios-alert-r1");
});

test("channel availability never assumes permission", () => {
  const a = channelAvailability();   // node: no window
  assert.equal(a.available, false);
  assert.equal(a.reason, "NOT_SUPPORTED");
});
