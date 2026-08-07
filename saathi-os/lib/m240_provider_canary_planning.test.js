import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, "..");
const page = path.join(root, "app/trading/provider-canary-planning/page.jsx");
const shell = path.join(root, "components/trading/TradingShell.jsx");

test("provider canary planning page exists", () => {
  assert.ok(fs.existsSync(page));
});

test("page is planning-only with authority labels", () => {
  const src = fs.readFileSync(page, "utf8");
  assert.match(src, /PLANNING ONLY/);
  assert.match(src, /NO REAL CONNECTIVITY/);
  assert.match(src, /NO CREDENTIALS/);
  assert.match(src, /CANARY NOT AUTHORIZED/);
  assert.match(src, /LIVE TRADING NOT AUTHORIZED/);
  assert.match(src, /data-testid="planning-only"/);
  assert.match(src, /provider-canary-planning/);
});

test("page has no credential form or oauth controls", () => {
  const src = fs.readFileSync(page, "utf8");
  assert.doesNotMatch(src, /type=["']password["']/i);
  assert.doesNotMatch(src, /oauth.?login/i);
  assert.doesNotMatch(src, /connect.?provider/i);
  assert.match(src, /Try Owner Sign-off \(must fail\)/);
  assert.match(src, /Try Activate Canary \(must fail\)/);
  assert.match(src, /Try Credentials \(must fail\)/);
});

test("trading shell links to provider canary planning", () => {
  const src = fs.readFileSync(shell, "utf8");
  assert.match(src, /\/trading\/provider-canary-planning/);
  assert.match(src, /Provider Canary Planning/);
});

test("package.json includes cert:m247 and unit test", () => {
  const pkg = JSON.parse(fs.readFileSync(path.join(root, "package.json"), "utf8"));
  assert.equal(typeof pkg.scripts["cert:m247"], "string");
  assert.match(pkg.scripts.test, /m240_provider_canary_planning/);
});
