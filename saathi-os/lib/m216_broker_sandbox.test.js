/**
 * M216–M223 frontend unit checks — Broker Sandbox Control Center.
 * Paper only. No live broker.
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const read = (p) => readFileSync(join(ROOT, p), "utf8");

describe("M216–M223 broker sandbox UI", () => {
  it("broker-sandbox page is sandbox-only / paper-only", () => {
    const src = read("app/trading/broker-sandbox/page.jsx");
    assert.match(src, /SANDBOX ONLY/);
    assert.match(src, /NO LIVE BROKER/);
    assert.match(src, /PAPER ONLY/);
    assert.match(src, /NO API CREDENTIALS/);
    assert.match(src, /CANNOT EXECUTE REAL ORDERS/);
    assert.match(src, /data-testid="sandbox-only"/);
    assert.match(src, /data-testid="no-live-broker"/);
    assert.match(src, /data-testid="bs-verdict"/);
    assert.match(src, /data-testid="bs-broker-registry"/);
    assert.match(src, /data-testid="bs-capability-viewer"/);
    assert.match(src, /data-testid="trust-center"/);
    assert.match(src, /data-testid="approval-pipeline"/);
    assert.match(src, /data-testid="credential-metadata"/);
    assert.match(src, /data-testid="sandbox-emulator"/);
    assert.match(src, /data-testid="recovery-center"/);
    assert.match(src, /data-testid="security-dashboard"/);
    assert.match(src, /data-testid="bs-audit-timeline"/);
    assert.match(src, /\/tg\/broker-sandbox\//);
    assert.doesNotMatch(src, /api_key\s*[:=]/i);
    assert.doesNotMatch(src, /LIVE_TRADING\s*=\s*true/);
  });

  it("tabs include broker-sandbox", () => {
    const src = read("components/trading/TradingShell.jsx");
    assert.match(src, /broker-sandbox/);
    assert.match(src, /Broker Sandbox/);
  });
});
