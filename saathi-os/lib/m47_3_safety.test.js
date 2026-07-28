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

describe("Trading operator workspace safety boundary (M62.8)", () => {
  const src = read("app/trading/page.jsx");
  it("is paper-only with live execution unavailable and no live-order entry", () => {
    // The M54 advisory-only placeholder is replaced by the real paper workspace.
    // The safety boundary is now TRUTHFUL: paper simulation available, live disabled.
    assert.match(src, /PAPER/);
    assert.match(src, /LIVE EXECUTION: UNAVAILABLE|Live execution unavailable/i);
    assert.match(src, /SIMULATION ONLY|Simulation-only/i);
    // never a live-order / live-broker control
    assert.doesNotMatch(src, /executeTrade|submitLiveOrder|liveBroker/);
    // must not resurrect the misleading "execution is not available" placeholder
    assert.doesNotMatch(src, /Trading execution is not available/);
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
