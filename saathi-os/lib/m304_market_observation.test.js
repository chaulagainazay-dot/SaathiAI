/**
 * M304–M311 Market Observation — frontend smoke checks.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const PAGE = join(ROOT, "app/trading/market-observation/page.jsx");
const SHELL = join(ROOT, "components/trading/TradingShell.jsx");

test("market-observation page exists", () => {
  assert.equal(existsSync(PAGE), true);
});

test("boundary labels", () => {
  const src = readFileSync(PAGE, "utf8");
  for (const n of [
    "READ-ONLY OBSERVATION",
    "VALIDATION — NOT TRADING",
    "OFFLINE-FIRST",
    "NO BROKER LOGIN",
    "NO OAUTH",
    "NO CREDENTIAL STORAGE",
    "NO ORDERS",
    "NO ACCOUNT ACCESS",
    "NO LIVE TRADING",
    "data-testid=\"validation-not-trading\"",
    "data-testid=\"refuse-broker-login\"",
    "data-testid=\"refuse-oauth\"",
    "data-testid=\"refuse-balances\"",
  ]) {
    assert.ok(src.includes(n), `missing ${n}`);
  }
});

test("no password form", () => {
  const src = readFileSync(PAGE, "utf8");
  assert.ok(!src.includes('type="password"'));
});

test("TradingShell has Market Observation tab", () => {
  const src = readFileSync(SHELL, "utf8");
  assert.ok(src.includes("/trading/market-observation"));
});

test("package.json has cert:m311", () => {
  const pkg = JSON.parse(readFileSync(join(ROOT, "package.json"), "utf8"));
  assert.ok(pkg.scripts["cert:m311"]);
  assert.ok(pkg.scripts.test.includes("m304_market_observation.test.js"));
});
