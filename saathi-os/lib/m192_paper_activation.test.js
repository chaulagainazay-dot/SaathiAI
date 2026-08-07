/**
 * M192–M199 — Paper activation UI safety labels.
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const read = (p) => readFileSync(join(root, p), "utf8");

const PAGES = [
  "app/trading/paper-portfolio/page.jsx",
  "app/trading/paper-orders/page.jsx",
  "app/trading/paper-journal/page.jsx",
  "app/trading/paper-risk/page.jsx",
  "app/trading/paper-approvals/page.jsx",
  "app/trading/paper-analytics/page.jsx",
  "app/trading/paper-reconcile/page.jsx",
];

describe("M192 paper activation UI", () => {
  for (const p of PAGES) {
    it(`${p} declares paper-only`, () => {
      const src = read(p);
      assert.match(src, /PAPER TRADING ONLY|paper-only/);
    });
  }

  it("TradingShell includes paper governance tabs", () => {
    const src = read("components/trading/TradingShell.jsx");
    for (const href of [
      "/trading/paper-portfolio",
      "/trading/paper-orders",
      "/trading/paper-journal",
      "/trading/paper-risk",
      "/trading/paper-approvals",
      "/trading/paper-analytics",
      "/trading/paper-reconcile",
    ]) {
      assert.match(src, new RegExp(href.replace(/\//g, "\\/")));
    }
  });

  it("approvals page blocks LLM approve messaging", () => {
    const src = read("app/trading/paper-approvals/page.jsx");
    assert.match(src, /LLM MAY NOT APPROVE|llm_may_approve/);
  });
});
