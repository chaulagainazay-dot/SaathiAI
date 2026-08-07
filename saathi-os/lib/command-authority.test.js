import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  normalizeTruthState,
  composeAuthorityStrip,
  mapVoiceSessionViewState,
  truthStateToBadgeStatus,
} from "./command-authority.js";

describe("command-authority", () => {
  it("normalizes truth states without inventing healthy", () => {
    assert.equal(normalizeTruthState(null), "UNKNOWN");
    assert.equal(normalizeTruthState("healthy"), "HEALTHY");
    assert.equal(normalizeTruthState("degraded"), "DEGRADED");
    assert.equal(normalizeTruthState("disabled"), "DISABLED");
    assert.equal(normalizeTruthState("stale"), "STALE");
    assert.equal(normalizeTruthState("weird-value"), "UNKNOWN");
  });

  it("maps voice session states only from real runtime fields", () => {
    assert.equal(mapVoiceSessionViewState(null, false), "OFF");
    assert.equal(mapVoiceSessionViewState(null, true), "READY");
    assert.equal(mapVoiceSessionViewState({ listening: true }, true), "LISTENING");
    assert.equal(mapVoiceSessionViewState({ speaking: true }, true), "SPEAKING");
    assert.equal(mapVoiceSessionViewState({ interrupted: true }, true), "INTERRUPTED");
    assert.equal(mapVoiceSessionViewState({ state: "THINKING" }, true), "THINKING");
    assert.equal(mapVoiceSessionViewState({ error: "x" }, true), "ERROR");
  });

  it("composes authority strip with paper-only and live orders disabled", () => {
    const strip = composeAuthorityStrip({
      apiBase: "http://127.0.0.1:8765",
      tradingAuth: true,
      tradingReady: true,
      tradingSummary: {
        accounts: 1,
        blockingBreakers: 0,
        unackAlerts: 0,
        critDrift: 0,
      },
      voicePrefsEnabled: true,
      voiceRuntime: { state: "IDLE" },
    });
    const byId = Object.fromEntries(strip.chips.map((c) => [c.id, c]));
    assert.equal(byId.live_orders.state, "DISABLED");
    assert.equal(byId.trading.state, "PAPER_ONLY");
    assert.equal(byId.execution.state, "GOVERNED");
    assert.equal(byId.environment.detail.includes("PRIVATE ALPHA") || byId.environment.state === "ACTIVE", true);
    assert.equal(byId.providers.state, "DISABLED");
  });

  it("marks TG blocked when breakers block", () => {
    const strip = composeAuthorityStrip({
      tradingAuth: true,
      tradingReady: true,
      tradingSummary: { accounts: 1, blockingBreakers: 2, unackAlerts: 0, critDrift: 0 },
    });
    const tg = strip.chips.find((c) => c.id === "tg");
    assert.equal(tg.state, "BLOCKED");
  });

  it("maps badge status for disabled without looking like error", () => {
    assert.equal(truthStateToBadgeStatus("DISABLED"), "neutral");
    assert.equal(truthStateToBadgeStatus("UNKNOWN"), "pending");
    assert.equal(truthStateToBadgeStatus("BLOCKED"), "error");
    assert.equal(truthStateToBadgeStatus("PAPER_ONLY"), "success");
  });

  it("never marks providers healthy from missing live cert", () => {
    const strip = composeAuthorityStrip({
      overview: { providers: { status: "healthy" } },
    });
    const p = strip.chips.find((c) => c.id === "providers");
    // policy: even if overview says healthy, we coerce away from HEALTHY for uncertified live
    assert.notEqual(p.state, "HEALTHY");
  });
});
