import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const read = (p) => readFileSync(join(root, p), "utf8");

describe("M200 durable paper UI", () => {
  for (const p of [
    "app/trading/paper-ops/page.jsx",
    "app/trading/paper-campaigns/page.jsx",
    "app/trading/paper-ledger/page.jsx",
    "app/trading/paper-recovery/page.jsx",
  ]) {
    it(`${p} paper-only`, () => {
      const src = read(p);
      assert.match(src, /PAPER TRADING ONLY|paper-only/);
    });
  }
  it("tabs include durable surfaces", () => {
    const src = read("components/trading/TradingShell.jsx");
    assert.match(src, /paper-ops/);
    assert.match(src, /paper-campaigns/);
    assert.match(src, /paper-ledger/);
    assert.match(src, /paper-recovery/);
  });
});
