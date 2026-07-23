import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  LEGACY_PARITY,
  CANONICAL_ROUTES,
  validateParityMatrix,
  redirectReadinessSummary,
} from "./m47_4_parity.js";
import { readFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

describe("M47.4 parity matrix integrity", () => {
  it("has 10 legacy rows and 10 canonical routes", () => {
    assert.equal(LEGACY_PARITY.length, 10);
    assert.equal(CANONICAL_ROUTES.length, 10);
  });

  it("validateParityMatrix has no errors", () => {
    assert.deepEqual(validateParityMatrix(), []);
  });

  it("no READY_TO_REDIRECT in M47.4", () => {
    assert.ok(LEGACY_PARITY.every((r) => r.classification !== "READY_TO_REDIRECT"));
  });

  it("redirect readiness summary shows zero ready", () => {
    const s = redirectReadinessSummary();
    assert.equal(s.readyToRedirect, 0);
  });
});

describe("M47.4 browser cert harness exists", () => {
  it("ships managed lifecycle script", () => {
    const p = join(root, "scripts/m47_4_browser_cert.mjs");
    assert.ok(existsSync(p));
    const src = readFileSync(p, "utf8");
    assert.match(src, /waitHealthy|chromium|CANONICAL|keyboard|shutdown|SIGTERM/);
    assert.match(src, /does not fabricate|No redirects|tradingAdvisory/i);
  });
});

describe("Trading still advisory after M47.3", () => {
  it("trading page boundary intact", () => {
    const src = readFileSync(join(root, "app/trading/page.jsx"), "utf8");
    assert.match(src, /Advisory only/i);
    assert.match(src, /NO_TRADING_AUTHORITY/);
  });
});
