/**
 * M232–M239 frontend unit checks — Integration Assurance Control Center.
 * REPRODUCIBILITY AND PLANNING ONLY. No real connectivity.
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const read = (p) => readFileSync(join(ROOT, p), "utf8");

describe("M232–M239 integration assurance UI", () => {
  it("integration-assurance page shows planning-only boundaries", () => {
    const src = read("app/trading/integration-assurance/page.jsx");
    assert.match(src, /REPRODUCIBILITY AND PLANNING ONLY/);
    assert.match(src, /NO REAL CONNECTIVITY/);
    assert.match(src, /NO CREDENTIALS/);
    assert.match(src, /NO PROVIDER ACCOUNT ACCESS/);
    assert.match(src, /NO ORDER CAPABILITY/);
    assert.match(src, /LIVE TRADING NOT AUTHORIZED/);
    assert.match(src, /integration-assurance/);
  });

  it("does not accept credentials or activate providers", () => {
    const src = read("app/trading/integration-assurance/page.jsx");
    assert.match(src, /CREDENTIAL FORM: NONE/);
    assert.match(src, /PROVIDER ACTIVATION ACTION: NONE/);
    assert.match(src, /OAUTH \/ PROVIDER LOGIN: NONE/);
    assert.match(src, /REAL_CONNECTIVITY_AUTHORIZED=false/);
    assert.doesNotMatch(src, /api_key\s*:/);
    assert.doesNotMatch(src, /enableLiveTrading\s*=\s*true/i);
  });

  it("TradingShell includes Integration Assurance tab", () => {
    const src = read("components/trading/TradingShell.jsx");
    assert.match(src, /\/trading\/integration-assurance/);
    assert.match(src, /Integration Assurance/);
  });

  it("cert:m239 script exists in package.json", () => {
    const pkg = JSON.parse(read("package.json"));
    assert.equal(pkg.scripts["cert:m239"], "node scripts/m239_integration_assurance_browser_cert.mjs");
  });
});
