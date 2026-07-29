/**
 * M166–M175 — Trading Guardian UI safety surfaces (paper only).
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const read = (p) => readFileSync(join(root, p), "utf8");

const PAGES = [
  "app/trading/regime/page.jsx",
  "app/trading/proposals/page.jsx",
  "app/trading/backtests/page.jsx",
  "app/trading/comparison/page.jsx",
  "app/trading/journal/page.jsx",
  "app/trading/policy/page.jsx",
];

describe("M166 TG UI paper-only labels", () => {
  for (const p of PAGES) {
    it(`${p} declares PAPER TRADING ONLY and NO LIVE ORDERS`, () => {
      const src = read(p);
      assert.match(src, /PAPER TRADING ONLY/);
      assert.match(src, /NO LIVE ORDERS/);
      assert.match(src, /SIMULATED FUNDS/);
    });
  }

  it("shared safety banner includes NO LIVE ORDERS and SIMULATED FUNDS", () => {
    const src = read("lib/trading.js");
    assert.match(src, /NO LIVE ORDERS/);
    assert.match(src, /SIMULATED FUNDS/);
    assert.match(src, /PAPER TRADING ONLY/);
  });

  it("TradingShell tabs include new TG research surfaces", () => {
    const src = read("components/trading/TradingShell.jsx");
    for (const href of [
      "/trading/regime",
      "/trading/proposals",
      "/trading/backtests",
      "/trading/comparison",
      "/trading/journal",
      "/trading/policy",
    ]) {
      assert.match(src, new RegExp(href.replace(/\//g, "\\/")));
    }
  });

  it("module registry keeps live_trading feature flag false", () => {
    const src = read("lib/modules/registry.js");
    assert.match(src, /live_trading:\s*false/);
    assert.match(src, /real_money:\s*false/);
    assert.match(src, /external_broker:\s*false/);
  });
});
