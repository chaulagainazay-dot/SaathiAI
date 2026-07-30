/**
 * M272–M279 Research Lab Control Center — frontend smoke checks.
 * RESEARCH ONLY. No broker/credential/order UI.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const PAGE = join(ROOT, "app/trading/research-lab/page.jsx");
const SHELL = join(ROOT, "components/trading/TradingShell.jsx");

test("research-lab page exists", () => {
  assert.equal(existsSync(PAGE), true);
});

test("research-lab page has research boundary labels", () => {
  const src = readFileSync(PAGE, "utf8");
  for (const needle of [
    "RESEARCH ONLY",
    "OFFLINE-FIRST",
    "NO BROKER CONNECTIVITY",
    "NO ACCOUNT ACCESS",
    "NO CREDENTIALS",
    "NO LIVE TRADING",
    "NO GUARANTEED PROFITABILITY",
    "PAPER CANDIDATE DOES NOT AUTHORISE ORDER EXECUTION",
    "HUMAN REVIEW REQUIRED",
    "data-testid=\"research-only\"",
    "data-testid=\"aapl-oos-failed\"",
    "data-testid=\"btc-oos-failed\"",
    "OUT_OF_SAMPLE_FAILED",
  ]) {
    assert.ok(src.includes(needle), `missing: ${needle}`);
  }
});

test("research-lab page has no broker connect / api key / order / oauth controls", () => {
  const src = readFileSync(PAGE, "utf8");
  assert.ok(!src.includes("type=\"password\""));
  assert.ok(!src.includes("OAuth login"));
  assert.ok(!src.includes("Place Order"));
  assert.ok(!src.includes("LIVE_READY"));
  assert.ok(!src.includes("PROFIT GUARANTEED"));
  assert.ok(!src.includes("GUARANTEED RETURN"));
  assert.ok(src.includes("refuse-broker"));
  assert.ok(src.includes("refuse-credentials"));
  assert.ok(src.includes("refuse-orders"));
  assert.ok(src.includes("refuse-canary"));
  assert.ok(src.includes("refuse-paper-exec"));
});

test("TradingShell includes Research Lab tab", () => {
  const src = readFileSync(SHELL, "utf8");
  assert.ok(src.includes("/trading/research-lab"));
  assert.ok(src.includes("Research Lab"));
});

test("package.json has cert:m279", () => {
  const pkg = JSON.parse(readFileSync(join(ROOT, "package.json"), "utf8"));
  assert.ok(pkg.scripts["cert:m279"]);
  assert.ok(pkg.scripts.test.includes("m272_research_lab.test.js"));
});
