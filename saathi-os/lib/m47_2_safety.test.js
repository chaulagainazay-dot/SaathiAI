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

  it("declares advisory-only and execution disabled", () => {
    assert.match(src, /Advisory only/i);
    assert.match(src, /Execution/i);
    assert.match(src, /Disabled/i);
    assert.match(src, /Not granted|not granted/i);
    assert.match(src, /Leverage/i);
    assert.match(src, /Withdrawal/i);
    assert.match(src, /Prohibited|prohibited/i);
  });

  it("has no order/trade/broker execute controls", () => {
    // Forbid actionable control patterns (not prose that forbids them)
    assert.doesNotMatch(src, /onClick=\{[^}]*trade/i);
    assert.doesNotMatch(src, /executeTrade|submitOrder|connectBroker|placeOrder/i);
    assert.doesNotMatch(src, /<Button[^>]*>\s*(Trade|Buy|Sell|Order)/i);
    assert.doesNotMatch(src, /type="submit"[^>]*>[\s\S]{0,40}(Buy|Sell|Order)/i);
  });

  it("uses authority and risk primitives", () => {
    assert.match(src, /AuthorityBadge/);
    assert.match(src, /RiskBadge/);
    assert.match(src, /BlockedState/);
  });
});

describe("Approvals honesty", () => {
  const src = read("app/approvals/page.jsx");

  it("does not treat unavailable as zero", () => {
    assert.match(src, /not treated as zero|not displayed as 0|not counted as zero/i);
    assert.match(src, /Unavailable|unavailable/);
    assert.match(src, /Not yet integrated|not yet integrated/i);
  });

  it("does not call decide from the list UI", () => {
    assert.doesNotMatch(src, /platformDecideApproval/);
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
