/**
 * M288–M295 Paper Simulation — frontend smoke checks.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const PAGE = join(ROOT, "app/trading/paper-simulation/page.jsx");
const SHELL = join(ROOT, "components/trading/TradingShell.jsx");

test("paper-simulation page exists", () => {
  assert.equal(existsSync(PAGE), true);
});

test("boundary labels present", () => {
  const src = readFileSync(PAGE, "utf8");
  for (const n of [
    "PAPER SIMULATION ONLY",
    "VIRTUAL EXCHANGE ONLY",
    "NO BROKER CONNECTIVITY",
    "NO REAL ORDER ROUTING",
    "NO LIVE TRADING",
    "NO API KEYS",
    "data-testid=\"paper-sim-only\"",
    "data-testid=\"run-bootstrap\"",
  ]) {
    assert.ok(src.includes(n), `missing ${n}`);
  }
});

test("no password form / place order live", () => {
  const src = readFileSync(PAGE, "utf8");
  assert.ok(!src.includes('type="password"'));
  assert.ok(src.includes("refuse-broker"));
  assert.ok(src.includes("refuse-real-orders"));
});

test("TradingShell has Paper Simulation tab", () => {
  const src = readFileSync(SHELL, "utf8");
  assert.ok(src.includes("/trading/paper-simulation"));
});

test("package.json has cert:m295", () => {
  const pkg = JSON.parse(readFileSync(join(ROOT, "package.json"), "utf8"));
  assert.ok(pkg.scripts["cert:m295"]);
  assert.ok(pkg.scripts.test.includes("m288_paper_simulation.test.js"));
});
