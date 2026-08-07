import { describe, it } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { CORE_NOTICE, coreActions } from "./core-os.js";

describe("SaathiOS Core unification frontend", () => {
  it("labels composition posture", () => {
    assert.match(CORE_NOTICE.unification, /compos|not a second/i);
    assert.match(CORE_NOTICE.yeti, /ExecutionGateway|read-only/i);
    assert.match(CORE_NOTICE.production, /not authorized/i);
  });

  it("calls authenticated core API namespace", async () => {
    const seen = [];
    const original = globalThis.fetch;
    globalThis.fetch = async (url, options) => {
      seen.push({ url: String(url), options });
      return new Response(JSON.stringify({ home: {}, results: [] }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    };
    try {
      await coreActions.home("tok");
      assert.match(seen[0].url, /\/api\/v1\/platform\/core\/home$/);
      await coreActions.search("tok", "approval");
      assert.match(seen[1].url, /\/api\/v1\/platform\/core\/search\?q=approval/);
      await coreActions.yeti("tok", "What should I do first today?");
      assert.match(seen[2].url, /\/api\/v1\/platform\/core\/yeti$/);
      assert.equal(seen[2].options.method, "POST");
    } finally {
      globalThis.fetch = original;
    }
  });

  it("operator home exposes unified surfaces", () => {
    const source = fs.readFileSync(
      new URL("../components/core/OperatorHome.jsx", import.meta.url),
      "utf8"
    );
    for (const text of [
      "Operator Home",
      "Universal Search",
      "Unified Yeti",
      "Notification Center",
      "Today",
      "Automations",
      "Open HCG",
      "IELTSAlert",
      "data-core-home",
      "can_mutate",
      'aria-live="polite"',
    ]) {
      assert.ok(source.includes(text), `missing ${text}`);
    }
  });

  it("command palette includes core destinations", () => {
    const source = fs.readFileSync(
      new URL("../components/CommandPalette.jsx", import.meta.url),
      "utf8"
    );
    assert.ok(source.includes("/platform/home"));
    assert.ok(source.includes("/apps/hcg"));
    assert.ok(source.includes("/apps/ielts"));
    assert.ok(source.includes("Operator Home"));
  });
});
