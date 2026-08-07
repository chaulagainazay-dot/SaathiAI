import { describe, it } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { formatPaisa, HCG_NOTICE, hcgActions } from "./hcg.js";

describe("HCG Operations frontend contract", () => {
  it("labels local-only limitations explicitly", () => {
    assert.match(HCG_NOTICE.data, /demo|certification/i);
    assert.match(HCG_NOTICE.qr, /manual/i);
    assert.match(HCG_NOTICE.money, /integer|paisa/i);
    assert.match(HCG_NOTICE.production, /not authorized/i);
  });

  it("formats integer paisa without binary float", () => {
    assert.equal(formatPaisa(18000), "180.00 NPR");
    assert.equal(formatPaisa(0), "0.00 NPR");
    assert.equal(formatPaisa(-1050), "-10.50 NPR");
  });

  it("mutations use authenticated HCG API namespace", async () => {
    const seen = [];
    const original = globalThis.fetch;
    globalThis.fetch = async (url, options) => {
      seen.push({ url: String(url), options });
      return new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    };
    try {
      await hcgActions.createOrder("test-token", {
        lines: [{ menu_item_id: "x", qty: 1, unit_price_minor: 100 }],
      });
      assert.match(seen[0].url, /\/api\/v1\/platform\/apps\/hcg\/orders$/);
      assert.equal(seen[0].options.method, "POST");
      assert.equal(seen[0].options.headers["X-Platform-Token"], "test-token");

      await hcgActions.payment("test-token", {
        order_id: "o1",
        amount_minor: 100,
        method: "CASH",
      });
      assert.match(seen[1].url, /\/api\/v1\/platform\/apps\/hcg\/payments$/);

      await hcgActions.yeti("test-token", "What were today’s sales?");
      assert.match(seen[2].url, /\/api\/v1\/platform\/apps\/hcg\/yeti$/);
    } finally {
      globalThis.fetch = original;
    }
  });

  it("workspace exposes POS, kitchen, shifts, and accessibility labels", () => {
    const source = fs.readFileSync(
      new URL("../components/hcg/HcgWorkspace.jsx", import.meta.url),
      "utf8"
    );
    for (const text of [
      "HCG Operations workspace",
      "Sign in required",
      "Order basket",
      "Kitchen queue",
      "Payment method",
      "QR payment reference",
      "Open shift",
      "ledger-backed",
      "Ask Yeti",
      "Create backup",
      "Application launcher",
      "derived from authoritative",
      'aria-live="polite"',
      'aria-label="HCG sections"',
    ]) {
      assert.ok(source.includes(text), `missing: ${text}`);
    }
  });
});
