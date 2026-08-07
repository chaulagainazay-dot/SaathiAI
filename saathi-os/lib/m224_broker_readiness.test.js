/**
 * M224–M231 frontend unit checks — Broker Readiness Control Center.
 * SIMULATION ONLY. No real connection. No real credentials.
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const read = (p) => readFileSync(join(ROOT, p), "utf8");

describe("M224–M231 broker readiness UI", () => {
  it("broker-readiness page is simulation-only / read-only", () => {
    const src = read("app/trading/broker-readiness/page.jsx");
    assert.match(src, /SIMULATION ONLY/);
    assert.match(src, /NO REAL CONNECTION/);
    assert.match(src, /NO REAL CREDENTIAL/);
    assert.match(src, /READ-ONLY ARCHITECTURE/);
    assert.match(src, /NO ORDER SUBMISSION/);
    assert.match(src, /LIVE TRADING NOT AUTHORIZED/);
    assert.match(src, /broker-readiness/);
  });

  it("does not accept raw secrets or enable trading", () => {
    const src = read("app/trading/broker-readiness/page.jsx");
    assert.match(src, /SECRET_MATERIAL_REJECTED/);
    assert.match(src, /ORDER SUBMISSION SURFACE: NONE/);
    assert.match(src, /ENABLE TRADING BUTTON: NONE/);
    assert.doesNotMatch(src, /place_order.*submit|enableLiveTrading\s*=\s*true/i);
    // No API path that stores secrets
    assert.doesNotMatch(src, /api_key:\s*secretAttempt/);
  });

  it("TradingShell includes Broker Readiness tab", () => {
    const src = read("components/trading/TradingShell.jsx");
    assert.match(src, /\/trading\/broker-readiness/);
    assert.match(src, /Broker Readiness/);
  });

  it("cert:m231 script exists in package.json", () => {
    const pkg = JSON.parse(read("package.json"));
    assert.equal(pkg.scripts["cert:m231"], "node scripts/m231_broker_readiness_browser_cert.mjs");
  });
});
