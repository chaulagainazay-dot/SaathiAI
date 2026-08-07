/**
 * M256–M263 Research Data Control Center — frontend smoke checks.
 * RESEARCH ONLY. No broker/credential/order UI.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const PAGE = join(ROOT, "app/trading/research-data/page.jsx");
const SHELL = join(ROOT, "components/trading/TradingShell.jsx");

test("research-data page exists", () => {
  assert.equal(existsSync(PAGE), true);
});

test("research-data page has research boundary labels", () => {
  const src = readFileSync(PAGE, "utf8");
  for (const needle of [
    "RESEARCH ONLY",
    "OFFLINE-FIRST",
    "NO BROKER CONNECTIVITY",
    "NO ACCOUNT ACCESS",
    "NO ORDER EXECUTION",
    "NO LIVE TRADING",
    "NO GUARANTEED PROFITABILITY",
    "data-testid=\"research-only\"",
    "data-testid=\"synthetic-label\"",
    "SYNTHETIC_TEST_DATA",
    "STRATEGY RESULTS DO NOT GUARANTEE FUTURE PERFORMANCE",
  ]) {
    assert.ok(src.includes(needle), `missing: ${needle}`);
  }
});

test("research-data page has no broker connect / api key / order / oauth controls", () => {
  const src = readFileSync(PAGE, "utf8");
  // Must not contain interactive broker/credential/order wiring beyond refusal probes
  assert.ok(!src.includes("type=\"password\""));
  assert.ok(!src.includes("OAuth login"));
  assert.ok(!src.includes("Place Order"));
  assert.ok(!src.includes("LIVE_READY"));
  assert.ok(!src.includes("PROFITABLE"));
  // Refusal probes are allowed
  assert.ok(src.includes("refuse-broker"));
  assert.ok(src.includes("refuse-credentials"));
  assert.ok(src.includes("refuse-orders"));
  assert.ok(src.includes("refuse-canary"));
});

test("TradingShell includes Research Data tab", () => {
  const src = readFileSync(SHELL, "utf8");
  assert.ok(src.includes('/trading/research-data'));
  assert.ok(src.includes("Research Data"));
});

test("package.json has cert:m263", () => {
  const pkg = JSON.parse(readFileSync(join(ROOT, "package.json"), "utf8"));
  assert.ok(pkg.scripts["cert:m263"]);
  assert.ok(pkg.scripts.test.includes("m256_market_data.test.js"));
});
