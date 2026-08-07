/**
 * M280–M287 Research Orchestrator — frontend smoke checks.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const PAGE = join(ROOT, "app/trading/research-orchestrator/page.jsx");
const SHELL = join(ROOT, "components/trading/TradingShell.jsx");

test("research-orchestrator page exists", () => {
  assert.equal(existsSync(PAGE), true);
});

test("research-orchestrator boundary labels", () => {
  const src = readFileSync(PAGE, "utf8");
  for (const needle of [
    "RESEARCH ONLY",
    "OFFLINE-FIRST",
    "DETERMINISTIC ORCHESTRATION",
    "NO BROKER CONNECTIVITY",
    "NO ORDER EXECUTION",
    "NO LIVE TRADING",
    "data-testid=\"research-only\"",
    "data-testid=\"run-bootstrap\"",
  ]) {
    assert.ok(src.includes(needle), `missing: ${needle}`);
  }
});

test("no password/oauth/order entry", () => {
  const src = readFileSync(PAGE, "utf8");
  assert.ok(!src.includes('type="password"'));
  assert.ok(!src.includes("Place Order"));
  assert.ok(src.includes("refuse-broker"));
});

test("TradingShell includes Research Orchestrator tab", () => {
  const src = readFileSync(SHELL, "utf8");
  assert.ok(src.includes("/trading/research-orchestrator"));
});

test("package.json has cert:m287", () => {
  const pkg = JSON.parse(readFileSync(join(ROOT, "package.json"), "utf8"));
  assert.ok(pkg.scripts["cert:m287"]);
  assert.ok(pkg.scripts.test.includes("m280_research_orchestrator.test.js"));
});
