import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  DEMO_BANNER,
  MODES,
  VOICE_STATES,
  demoPortfolio,
  demoRisk,
  mapVoiceCommand,
} from "./design-lab-demo.js";

describe("design-lab-demo", () => {
  it("labels all demo data as MOCK", () => {
    assert.match(DEMO_BANNER, /DEMO/);
    assert.equal(demoPortfolio.source, "DEMO_MOCK");
    assert.equal(demoPortfolio.mode, "PAPER");
    assert.equal(demoPortfolio.live_execution, "UNAVAILABLE");
  });

  it("uses T-NEXT-shaped field names", () => {
    for (const k of [
      "paper_nav",
      "cash",
      "realized_pnl",
      "unrealized_pnl",
      "drawdown",
      "gross_exposure",
      "net_exposure",
      "reconciliation",
    ]) {
      assert.ok(k in demoPortfolio, k);
    }
    assert.equal(demoRisk.label, "PAPER RISK");
    assert.ok(Array.isArray(demoRisk.risk_budget_consumed));
  });

  it("voice states match VoiceSession vocabulary", () => {
    for (const s of [
      "IDLE",
      "READY",
      "LISTENING",
      "TRANSCRIBING",
      "THINKING",
      "SPEAKING",
      "INTERRUPTING",
      "DEGRADED",
      "ERROR",
    ]) {
      assert.ok(VOICE_STATES.includes(s));
    }
  });

  it("maps navigation utterances without inventing live authority", () => {
    assert.equal(mapVoiceCommand("show portfolio risk").mode, "investments");
    assert.equal(mapVoiceCommand("show evidence").mode, "evidence");
    assert.equal(mapVoiceCommand("Stop now").voice, "INTERRUPTING");
    assert.equal(mapVoiceCommand("go back to command").mode, "command");
    assert.ok(MODES.length === 4);
  });

  it("risk contract stays paper", () => {
    assert.equal(demoRisk.mode, "PAPER");
    assert.equal(demoRisk.live_execution, "UNAVAILABLE");
  });
});
