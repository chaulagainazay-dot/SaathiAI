/**
 * M184–M191 — Historical research UI safety surfaces (paper only).
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const read = (p) => readFileSync(join(root, p), "utf8");

const PAGES = [
  "app/trading/historical/page.jsx",
  "app/trading/monte-carlo/page.jsx",
  "app/trading/qualification/page.jsx",
];

describe("M184 TG historical research UI", () => {
  for (const p of PAGES) {
    it(`${p} declares paper research and no live orders`, () => {
      const src = read(p);
      assert.match(src, /PAPER RESEARCH ONLY/);
      assert.match(src, /NO LIVE ORDERS/);
    });
  }

  it("TradingShell includes historical, monte-carlo, qualification tabs", () => {
    const src = read("components/trading/TradingShell.jsx");
    for (const href of [
      "/trading/historical",
      "/trading/monte-carlo",
      "/trading/qualification",
    ]) {
      assert.match(src, new RegExp(href.replace(/\//g, "\\/")));
    }
  });

  it("qualification page blocks live claims", () => {
    const src = read("app/trading/qualification/page.jsx");
    assert.match(src, /OWNER APPROVAL REQUIRED/);
    assert.match(src, /ELIGIBILITY/);
    assert.match(src, /llm_may_approve/);
  });

  it("historical page references local import path", () => {
    const src = read("app/trading/historical/page.jsx");
    assert.match(src, /historical\/import|data import|List datasets/);
    assert.match(src, /HISTORICAL RESULTS ARE NOT FUTURE RESULTS/);
  });
});
