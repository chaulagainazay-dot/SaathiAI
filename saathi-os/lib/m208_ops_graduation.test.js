import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const read = (p) => readFileSync(join(root, p), "utf8");

describe("M208–M215 ops graduation UI", () => {
  it("ops-graduation page is paper-only", () => {
    const src = read("app/trading/ops-graduation/page.jsx");
    assert.match(src, /PAPER ONLY/);
    assert.match(src, /NO LIVE TRADING/);
    assert.match(src, /NO AUTO LIVE PROMOTION/);
    assert.match(src, /ops\/dashboard/);
    assert.match(src, /ops\/health/);
    assert.match(src, /ops\/verdict/);
    assert.match(src, /Campaign Overview/);
    assert.match(src, /Graduation Status/);
    assert.match(src, /never auto-applied/);
  });

  it("tabs include ops-graduation", () => {
    const src = read("components/trading/TradingShell.jsx");
    assert.match(src, /ops-graduation/);
  });
});
