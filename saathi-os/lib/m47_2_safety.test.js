/**
 * M47.2 safety boundary tests — trading route source + approvals honesty helpers.
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

function read(rel) {
  return readFileSync(join(root, rel), "utf8");
}

describe("Trading Guardian page safety", () => {
  const src = read("app/trading/page.jsx");

  it("declares paper-only simulation with live execution disabled (M62.8)", () => {
    // M62.8 replaces the M54 advisory placeholder with a real paper workspace.
    // The boundary is truthful: paper execution available, live execution disabled.
    assert.match(src, /PAPER/);
    assert.match(src, /SIMULATION ONLY/i);
    assert.match(src, /LIVE EXECUTION: UNAVAILABLE|Live execution unavailable/i);
    assert.match(src, /long-only|LONG-ONLY/i);
    assert.match(src, /localhost/i);
  });

  it("has no order/trade/broker execute controls", () => {
    // Forbid actionable control patterns (not prose that forbids them)
    assert.doesNotMatch(src, /onClick=\{[^}]*trade/i);
    assert.doesNotMatch(src, /executeTrade|submitOrder|connectBroker|placeOrder/i);
    assert.doesNotMatch(src, /<Button[^>]*>\s*(Trade|Buy|Sell|Order)/i);
    assert.doesNotMatch(src, /type="submit"[^>]*>[\s\S]{0,40}(Buy|Sell|Order)/i);
  });

  it("carries explicit paper-only authority framing (M62.8)", () => {
    // The real paper workspace replaces the placeholder badges with a truthful,
    // persistent safety frame: paper environment, simulation authority, live disabled.
    assert.match(src, /SafetyBanner/);
    assert.match(src, /ENVIRONMENT: PAPER/);
    assert.match(src, /AUTHORITY: SIMULATION ONLY/);
    assert.match(src, /LIVE EXECUTION: UNAVAILABLE/);
  });
});

describe("Approvals honesty", () => {
  const src = read("app/approvals/page.jsx");

  it("does not treat unavailable as zero", () => {
    assert.match(src, /not shown as zero|not displayed as zero|unavailable ≠ 0|not treated as zero/i);
    assert.match(src, /Unavailable|unavailable/);
    assert.match(src, /not_integrated|Not yet integrated|not yet integrated/i);
  });

  it("gates decide behind ConfirmDialog (no silent decide)", () => {
    // M47.3: authorized decide allowed only after ConfirmDialog confirmation
    assert.match(src, /ConfirmDialog/);
    assert.match(src, /platformDecideApproval/);
    assert.match(src, /explicit confirmation|Confirm approval/i);
  });
});

describe("Command palette safety", () => {
  const src = read("components/CommandPalette.jsx");

  it("removes misleading approve→finance routing", () => {
    assert.doesNotMatch(src, /Approve recommendation[\s\S]*\/finance/);
    assert.match(src, /\/approvals/);
    assert.match(src, /\/command/);
    assert.match(src, /no direct execution/i);
  });
});

describe("TopBar approvals honesty", () => {
  const src = read("components/TopBar.jsx");

  it("shows unavailable rather than fabricated zero on failure", () => {
    assert.match(src, /Approvals unavailable/);
    assert.match(src, /status: "unavailable"/);
  });
});

describe("Settings experience mode boundary", () => {
  const src = read("app/settings/page.jsx");

  it("states experience does not change authority", () => {
    assert.match(src, /Does not unlock actions or bypass approvals|Authority unchanged/i);
  });
});

describe("Shell keyboard + mobile", () => {
  const shell = read("components/Shell.jsx");
  const mobile = read("components/mobile/MobileTabBar.jsx");

  it("Esc closes copilot; ] toggles", () => {
    assert.match(shell, /closeCopilot/);
    assert.match(shell, /toggleCopilot/);
    assert.match(shell, /"]"/);
  });

  it("mobile uses MOBILE_TABS", () => {
    assert.match(mobile, /MOBILE_TABS/);
    assert.match(mobile, /from "@\/lib\/navigation"/);
    assert.match(mobile, /onCopilot/);
  });
});
