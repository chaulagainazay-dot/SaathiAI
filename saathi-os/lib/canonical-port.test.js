// Canonical local frontend port guard — asserts SaathiOS local UI is :3100,
// not the retired :3000, so the split-brain (stale :3000 build) cannot silently
// return. Prod (Oracle VM) keeps PORT=3000 via its own service env, so `start`
// must stay PORT-driven (no hard-coded -p) rather than pinned to 3100.
import { test } from "node:test";
import assert from "node:assert";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const pkg = JSON.parse(readFileSync(join(here, "..", "package.json"), "utf8"));
const startLocal = readFileSync(join(here, "..", "..", "scripts", "start_local.sh"), "utf8");

test("dev script serves the canonical :3100, never :3000", () => {
  assert.match(pkg.scripts.dev, /-p 3100\b/, "dev must use -p 3100");
  assert.doesNotMatch(pkg.scripts.dev, /-p 3000\b/, "dev must not pin :3000");
});

test("start defaults to :3100 locally but honors PORT (prod override)", () => {
  // bare `npm start` (no PORT) must not fall back to Next's :3000 default.
  assert.match(pkg.scripts.start, /\$\{PORT:-3100\}/, "start must default to 3100 via ${PORT:-3100}");
  assert.doesNotMatch(pkg.scripts.start, /-p 3000\b/, "start must not hard-code :3000");
});

test("local launcher pins the UI to :3100 and does not gate on :3000", () => {
  assert.match(startLocal, /export PORT=3100\b/, "start_local.sh must export PORT=3100");
  assert.doesNotMatch(startLocal, /localhost:3000/, "start_local.sh must not reference localhost:3000");
});
