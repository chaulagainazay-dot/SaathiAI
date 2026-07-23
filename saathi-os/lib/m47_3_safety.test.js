import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const read = (rel) => readFileSync(join(root, rel), "utf8");

describe("Home attention-first", () => {
  const src = read("app/page.jsx");
  it("uses attention hook and M1 states", () => {
    assert.match(src, /useAttentionHome/);
    assert.match(src, /LoadingState|EmptyState|ErrorState/);
    assert.match(src, /Needs attention|What needs attention/i);
    assert.match(src, /Unavailable/);
  });
  it("does not call platformDecide or execute from Home", () => {
    assert.doesNotMatch(src, /platformDecideApproval|platformExecute/);
  });
});

describe("dialogs exist", () => {
  const src = read("components/ui.jsx");
  it("exports ConfirmDialog and DestructiveDialog", () => {
    assert.match(src, /export function ConfirmDialog/);
    assert.match(src, /export function DestructiveDialog/);
    assert.match(src, /aria-modal/);
    assert.match(src, /Escape/);
  });
});

describe("Trading Guardian still advisory", () => {
  const src = read("app/trading/page.jsx");
  it("keeps advisory-only boundary", () => {
    assert.match(src, /Advisory only/i);
    assert.match(src, /NO_TRADING_AUTHORITY/);
    assert.doesNotMatch(src, /executeTrade|submitOrder/);
  });
});

describe("high-traffic pages use primitives", () => {
  for (const p of ["app/missions/page.jsx", "app/projects/page.jsx", "app/command/page.jsx", "app/monitoring/page.jsx"]) {
    it(`${p} imports LoadingState or ErrorState`, () => {
      const src = read(p);
      assert.match(src, /LoadingState|ErrorState|EmptyState/);
      assert.match(src, /StatusBadge|Button/);
    });
  }
});
