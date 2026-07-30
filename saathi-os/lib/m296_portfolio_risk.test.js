/**
 * M296–M303 Portfolio Risk — frontend smoke checks.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const PAGE = join(ROOT, "app/trading/portfolio-risk/page.jsx");
const SHELL = join(ROOT, "components/trading/TradingShell.jsx");

test("portfolio-risk page exists", () => {
  assert.equal(existsSync(PAGE), true);
});

test("boundary labels", () => {
  const src = readFileSync(PAGE, "utf8");
  for (const n of [
    "PAPER / RESEARCH ONLY",
    "NOT INVESTMENT ADVICE",
    "NOT REGULATORY-GRADE RISK",
    "NO BROKER CONNECTIVITY",
    "NO ORDER EXECUTION",
    "NO LIVE TRADING",
    "data-testid=\"not-advice\"",
    "data-testid=\"run-bootstrap\"",
  ]) {
    assert.ok(src.includes(n), `missing ${n}`);
  }
});

test("no password / refuses present", () => {
  const src = readFileSync(PAGE, "utf8");
  assert.ok(!src.includes('type="password"'));
  assert.ok(src.includes("refuse-broker"));
  assert.ok(src.includes("refuse-orders"));
});

test("TradingShell has Portfolio Risk tab", () => {
  const src = readFileSync(SHELL, "utf8");
  assert.ok(src.includes("/trading/portfolio-risk"));
});

test("package.json has cert:m303", () => {
  const pkg = JSON.parse(readFileSync(join(ROOT, "package.json"), "utf8"));
  assert.ok(pkg.scripts["cert:m303"]);
  assert.ok(pkg.scripts.test.includes("m296_portfolio_risk.test.js"));
});
