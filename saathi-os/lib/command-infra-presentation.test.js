/**
 * /command must render infrastructure health truthfully.
 *
 * Three defects lived in three adjacent lines of composeSystemStrip:
 *
 *   1. `value: infra?.models || "BOUND"` handed the backend's array of
 *      `{ id, available, light }` objects straight to a React child slot.
 *      React threw error #31 and the Command Center's main content did not
 *      render — the shell chrome around it did, so the page looked alive.
 *
 *   2. `status: infra?.ok === false ? "DEGRADED" : "HEALTHY"` read a field the
 *      backend never sends. `ok` exists only as a local fetch-failure sentinel
 *      the command hook substitutes for a payload, so on every successful
 *      fetch the chip reported HEALTHY regardless of how many models were
 *      actually available — including when none were.
 *
 *   3. `status: infra?.gateway === "down" ? ...` read a field no producer
 *      anywhere writes, so the gateway chip was a hardcoded green "EG".
 *
 * Underneath all three is a property of the backend aggregate: its percentage
 * helper returns 100 for an empty section, so an unreported section scores
 * perfect. Presentation therefore counts evidence and never trusts a score to
 * establish health.
 *
 * Fixtures below use the exact shapes returned by
 * GET /api/v1/infrastructure/health.
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  composeSystemStrip,
  summarizeInfraModels,
  summarizeInfraOverall,
  composeGatewayChip,
} from "./command-read-model.js";

/**
 * A payload shaped exactly like the live endpoint's.
 * Key presence, not value, decides an override — the tests need to pass an
 * explicit `undefined` to model a section the backend omitted.
 */
function infraFixture(overrides = {}) {
  const has = (key) => Object.prototype.hasOwnProperty.call(overrides, key);
  const { models, browser, connectors, conversation, score } = overrides;
  return {
    models: has("models")
        ? models
        : [
            { id: "anthropic/claude", available: true, light: "🟢" },
            { id: "openai/gpt-4o", available: false, light: "🔴" },
          ],
    browser: has("browser")
        ? browser
        : [
            { id: "http", available: true, light: "🟢" },
            { id: "playwright", available: false, light: "🔴" },
          ],
    connectors: has("connectors")
        ? connectors
        : [
            {
              id: "gmail",
              status: "ok",
              light: "🟢",
              detail: "",
              display_name: "Gmail",
              healthy: true,
              authenticated: true,
              category: "mail",
              capabilities: [],
              last_error: null,
              last_success: null,
              latency_ms: 12,
              quota_remaining: null,
            },
          ],
    conversation: has("conversation")
        ? conversation
        : {
            voice: { available: true, light: "🟢" },
            stt: { driver: "echo", available: true, light: "🟢" },
            tts: { driver: "silent", available: true, light: "🟢" },
            wakeword: { available: false, light: "🟡" },
            sessions: 0,
          },
    score: has("score")
        ? score
        : { models: 50, browser: 60, connectors: 100, voice: 100, overall: 78 },
  };
}

/* ------------------------------------------------------------------ */
/* the crash itself                                                     */
/* ------------------------------------------------------------------ */

describe("the models chip is renderable", () => {
  it("never publishes an object or array as the chip value", () => {
    const cases = [
      infraFixture(),
      infraFixture({ models: [] }),
      infraFixture({ models: undefined }),
      infraFixture({ models: { anthropic: true } }),
      infraFixture({ models: null }),
      null,
      { ok: false },
    ];
    for (const infra of cases) {
      const strip = composeSystemStrip({ infra });
      for (const key of ["models", "infrastructure", "gateway"]) {
        assert.equal(
          typeof strip[key].value,
          "string",
          `${key}.value must be a string; an object here is React error #31`
        );
      }
    }
  });

  it("does not stringify the array into [object Object]", () => {
    const strip = composeSystemStrip({ infra: infraFixture() });
    assert.doesNotMatch(strip.models.value, /\[object/);
  });

  it("keeps the structured list beside the scalar", () => {
    const infra = infraFixture();
    const chip = summarizeInfraModels(infra);
    assert.deepEqual(chip.list, infra.models, "downstream inspection must survive");
    assert.equal(chip.value, "1/2");
  });
});

/* ------------------------------------------------------------------ */
/* the eight required cases                                             */
/* ------------------------------------------------------------------ */

describe("models availability is counted, not assumed", () => {
  it("missing models section reports nothing and is not healthy", () => {
    const chip = summarizeInfraModels(infraFixture({ models: null }));
    assert.equal(chip.value, "NOT REPORTED");
    assert.notEqual(chip.status, "HEALTHY");
  });

  it("a non-array models section is invalid data, not a crash", () => {
    for (const malformed of ["8 models", 8, { anthropic: true }, true]) {
      const chip = summarizeInfraModels(infraFixture({ models: malformed }));
      assert.equal(chip.value, "INVALID DATA");
      assert.equal(chip.status, "DEGRADED");
      assert.equal(chip.list, null);
    }
  });

  it("an empty inventory is 0/0 and never healthy", () => {
    const chip = summarizeInfraModels(infraFixture({ models: [], score: { models: 100, overall: 100 } }));
    assert.equal(chip.value, "0/0");
    assert.notEqual(chip.status, "HEALTHY");
    assert.equal(
      chip.scorePercent,
      100,
      "the backend's vacuous 100 is carried, but it does not decide status"
    );
  });

  it("one available model reads 1/1 and healthy", () => {
    const chip = summarizeInfraModels(
      infraFixture({ models: [{ id: "ollama/local", available: true, light: "🟢" }] })
    );
    assert.equal(chip.value, "1/1");
    assert.equal(chip.status, "HEALTHY");
  });

  it("one unavailable model reads 0/1 and degraded", () => {
    const chip = summarizeInfraModels(
      infraFixture({ models: [{ id: "ollama/local", available: false, light: "🔴" }] })
    );
    assert.equal(chip.value, "0/1");
    assert.equal(chip.status, "DEGRADED");
  });

  it("a mixed list reports the exact counts", () => {
    const models = [
      { id: "a", available: true, light: "🟢" },
      { id: "b", available: false, light: "🔴" },
      { id: "c", available: true, light: "🟢" },
      { id: "d", available: false, light: "🔴" },
      { id: "e", available: false, light: "🔴" },
    ];
    const chip = summarizeInfraModels(infraFixture({ models }));
    assert.equal(chip.value, "2/5");
    assert.equal(chip.total, 5);
    assert.equal(chip.available, 2);
    assert.equal(chip.status, "DEGRADED");
  });

  it("a missing or out-of-range score keeps the count and invents nothing", () => {
    for (const score of [undefined, null, {}, { models: "50" }, { models: 1.5 }, { models: -1 }, { models: 101 }]) {
      const chip = summarizeInfraModels(infraFixture({ score }));
      assert.equal(chip.value, "1/2", "the count is independent of the score");
      assert.equal(chip.scorePercent, null, "no score is invented");
    }
  });

  it("only a boolean true counts as available", () => {
    const models = [
      { id: "a", available: "yes", light: "🟢" },
      { id: "b", available: 1, light: "🟢" },
      { id: "c", available: {}, light: "🟢" },
      { id: "d", light: "🔴" },
      { id: "e", available: true, light: "🟢" },
    ];
    const chip = summarizeInfraModels(infraFixture({ models }));
    assert.equal(chip.value, "1/5", "truthy junk is not an available model");
    assert.equal(chip.status, "DEGRADED");
  });

  it("a failed fetch reports nothing rather than guessing", () => {
    const chip = summarizeInfraModels({ ok: false });
    assert.equal(chip.value, "NOT REPORTED");
    assert.equal(chip.status, "UNAVAILABLE");
  });

  it("the real live payload shape produces 0/8 when nothing has keys", () => {
    const models = [
      "anthropic/claude",
      "openai/gpt-4o",
      "deepseek/deepseek-chat",
      "glm/glm-4.6",
      "qwen/qwen-2.5-72b",
      "gemini/3.5-flash",
      "groq/llama-3.3-70b",
      "ollama/local",
    ].map((id) => ({ id, available: false, light: "🔴" }));
    const chip = summarizeInfraModels(infraFixture({ models, score: { models: 0, overall: 50 } }));
    assert.equal(chip.value, "0/8");
    assert.equal(chip.status, "DEGRADED");
    assert.equal(chip.scorePercent, 0);
  });
});

/* ------------------------------------------------------------------ */
/* overall infrastructure                                               */
/* ------------------------------------------------------------------ */

describe("overall infrastructure health is evidence-gated", () => {
  it("uses the backend aggregate when evidence exists", () => {
    const chip = summarizeInfraOverall(infraFixture());
    assert.equal(chip.value, "78%");
    assert.equal(chip.status, "DEGRADED");
    assert.equal(chip.percent, 78);
  });

  it("is healthy only at a full score with real evidence", () => {
    const chip = summarizeInfraOverall(
      infraFixture({ score: { models: 100, browser: 100, connectors: 100, voice: 100, overall: 100 } })
    );
    assert.equal(chip.status, "HEALTHY");
    assert.equal(chip.value, "100%");
  });

  it("refuses a vacuous 100 from an entirely empty snapshot", () => {
    // Every backend section scores 100 when empty, so the aggregate reads
    // perfect for a platform that reported nothing at all.
    const chip = summarizeInfraOverall({
      models: [],
      browser: [],
      connectors: [],
      conversation: {},
      score: { models: 100, browser: 100, connectors: 100, voice: 100, overall: 100 },
    });
    assert.equal(chip.value, "NOT REPORTED");
    assert.notEqual(chip.status, "HEALTHY");
  });

  it("an empty conversation dictionary is not evidence", () => {
    const chip = summarizeInfraOverall({
      models: [],
      browser: [],
      connectors: [],
      conversation: { voice: {}, stt: {}, tts: {}, wakeword: {}, sessions: 0 },
      score: { overall: 100 },
    });
    assert.equal(chip.value, "NOT REPORTED");
  });

  it("a conversation section reporting a boolean is evidence", () => {
    const chip = summarizeInfraOverall({
      models: [],
      browser: [],
      connectors: [],
      conversation: { voice: { available: false, light: "🔴" }, sessions: 0 },
      score: { overall: 25 },
    });
    assert.equal(chip.value, "25%");
    assert.equal(chip.status, "DEGRADED");
  });

  it("a malformed overall score with real evidence is invalid data, not health", () => {
    for (const score of [undefined, null, {}, { overall: "78" }, { overall: 101 }, { overall: -3 }]) {
      const chip = summarizeInfraOverall(infraFixture({ score }));
      assert.equal(chip.value, "INVALID DATA");
      assert.notEqual(chip.status, "HEALTHY");
    }
  });

  it("a failed fetch reports nothing", () => {
    assert.equal(summarizeInfraOverall({ ok: false }).value, "NOT REPORTED");
    assert.equal(summarizeInfraOverall(null).value, "NOT REPORTED");
  });
});

/* ------------------------------------------------------------------ */
/* gateway                                                              */
/* ------------------------------------------------------------------ */

describe("the gateway chip reports what it knows, which is nothing", () => {
  it("never invents a gateway state", () => {
    const chip = composeGatewayChip();
    assert.equal(chip.value, "NOT REPORTED");
    assert.equal(chip.status, "UNAVAILABLE");
    assert.notEqual(chip.value, "EG");
    assert.notEqual(chip.status, "HEALTHY");
  });

  it("does not move with model, connector or overall health", () => {
    const healthy = composeSystemStrip({
      infra: infraFixture({ score: { models: 100, browser: 100, connectors: 100, voice: 100, overall: 100 } }),
    });
    const broken = composeSystemStrip({ infra: { ok: false } });
    assert.deepEqual(healthy.gateway, broken.gateway, "gateway must not track other sections");
  });
});

/* ------------------------------------------------------------------ */
/* nothing else in the strip moved                                      */
/* ------------------------------------------------------------------ */

describe("command authority is unchanged", () => {
  it("keeps the paper, trading guardian, recon, risk and voice chips intact", () => {
    const strip = composeSystemStrip({
      portfolio: { portfolio_status: "OK" },
      risk: { risk_status: "OK" },
      voiceState: "READY",
      infra: infraFixture(),
    });
    assert.equal(strip.paper.value, "PAPER");
    assert.equal(strip.paper.status, "HEALTHY");
    assert.equal(strip.trading_guardian.value, "SAFE");
    assert.equal(strip.risk.value, "OK");
    assert.equal(strip.voice.value, "READY");
    assert.equal(strip.provenance, "DERIVED");
  });

  it("still blocks on reconciliation regardless of infrastructure", () => {
    const strip = composeSystemStrip({
      portfolio: { portfolio_status: "RECONCILIATION_REQUIRED" },
      infra: infraFixture({ score: { overall: 100 } }),
    });
    assert.equal(strip.recon.status, "BLOCKED");
  });
});
