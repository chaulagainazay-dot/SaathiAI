/**
 * M312–M319 Connectivity Governance frontend unit tests.
 * GOVERNANCE ONLY — no secret fields, no connect controls as inputs.
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const pagePath = join(__dirname, "../app/trading/connectivity-governance/page.jsx");
const page = readFileSync(pagePath, "utf8");

describe("M312 connectivity governance UI", () => {
  it("page exists and is governance-only", () => {
    assert.match(page, /GOVERNANCE ONLY/);
    assert.match(page, /NO PROVIDER CONNECTION/);
    assert.match(page, /connectivity-governance/);
  });

  it("has no secret-entry fields", () => {
    assert.doesNotMatch(page, /type=["']password["']/i);
    assert.doesNotMatch(page, /name=["']api_key["']/i);
    assert.doesNotMatch(page, /name=["']api_secret["']/i);
    assert.doesNotMatch(page, /name=["']password["']/i);
    assert.doesNotMatch(page, /placeholder=["'][^"']*api[_-]?key/i);
  });

  it("renders authority and maturity markers", () => {
    assert.match(page, /cg-authority-locks/);
    assert.match(page, /GOVERNANCE_ONLY/);
    assert.match(page, /approval_does_not_equal_activation/);
    assert.match(page, /raw_credentials_forbidden/);
  });

  it("has refuse controls not connect/order activation", () => {
    assert.match(page, /Refuse Connect/);
    assert.match(page, /Refuse OAuth/);
    assert.match(page, /Refuse Order/);
    assert.match(page, /Refuse Canary/);
    assert.doesNotMatch(page, /Enable Live Trading/);
    assert.doesNotMatch(page, /Activate Canary/);
  });
});
