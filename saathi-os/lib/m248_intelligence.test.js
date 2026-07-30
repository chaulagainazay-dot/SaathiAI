import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, "..");
const page = path.join(root, "app/trading/intelligence/page.jsx");
const shell = path.join(root, "components/trading/TradingShell.jsx");

test("intelligence command center page exists", () => {
  assert.ok(fs.existsSync(page));
});

test("page is paper-only with authority labels", () => {
  const src = fs.readFileSync(page, "utf8");
  assert.match(src, /PAPER ONLY/);
  assert.match(src, /NO BROKER CONNECTIVITY/);
  assert.match(src, /NO API KEYS/);
  assert.match(src, /NO LIVE MARKET ACCESS/);
  assert.match(src, /NO ORDER EXECUTION/);
  assert.match(src, /NO LIVE TRADING/);
  assert.match(src, /data-testid="paper-only"/);
  assert.match(src, /\/tg\/intelligence/);
});

test("page has no credential form or broker connect controls", () => {
  const src = fs.readFileSync(page, "utf8");
  assert.doesNotMatch(src, /type=["']password["']/i);
  assert.doesNotMatch(src, /oauth.?login/i);
  assert.match(src, /Try Broker Connect \(must fail\)/);
  assert.match(src, /Try Credentials \(must fail\)/);
  assert.match(src, /Try Order \(must fail\)/);
  assert.match(src, /Strategy Library/);
  assert.match(src, /Investment Committee/);
  assert.match(src, /Monte Carlo/);
  assert.match(src, /Walk-Forward/);
});

test("trading shell links to portfolio intelligence", () => {
  const src = fs.readFileSync(shell, "utf8");
  assert.match(src, /\/trading\/intelligence/);
  assert.match(src, /Portfolio Intelligence/);
});

test("package.json includes cert:m255 and unit test", () => {
  const pkg = JSON.parse(fs.readFileSync(path.join(root, "package.json"), "utf8"));
  assert.equal(typeof pkg.scripts["cert:m255"], "string");
  assert.match(pkg.scripts.test, /m248_intelligence/);
});
