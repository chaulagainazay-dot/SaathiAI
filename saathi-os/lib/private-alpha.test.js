import { describe, it } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.join(HERE, "..", "..");

describe("Private alpha release packaging", () => {
  it("ships saathi-alpha CLI with localhost lifecycle delegation", () => {
    const cli = path.join(REPO, "bin", "saathi-alpha");
    assert.ok(fs.existsSync(cli));
    const src = fs.readFileSync(cli, "utf8");
    assert.match(src, /saathi-local/);
    assert.doesNotMatch(src, /0\.0\.0\.0/);
    assert.match(src, /NOT_AUTHORIZED|production NOT_AUTHORIZED/i);
  });

  it("documents private alpha release set", () => {
    for (const name of [
      "PRIVATE_ALPHA_RELEASE.md",
      "PRIVATE_ALPHA_INSTALL.md",
      "PRIVATE_ALPHA_OPERATIONS.md",
      "PRIVATE_ALPHA_BACKUP_RESTORE.md",
      "PRIVATE_ALPHA_AUTOMATIONS.md",
      "PRIVATE_ALPHA_CERTIFICATION.md",
      "PRIVATE_ALPHA_LIMITATIONS.md",
    ]) {
      const p = path.join(REPO, "docs", name);
      assert.ok(fs.existsSync(p), name);
      const text = fs.readFileSync(p, "utf8");
      assert.match(
        text,
        /not production|production disabled|production.?authorized.*false|NOT_AUTHORIZED|production not authorized/i
      );
    }
  });

  it("m165 browser cert script is fail-closed on production", () => {
    const p = path.join(HERE, "..", "scripts", "m165_private_alpha_browser_cert.mjs");
    assert.ok(fs.existsSync(p));
    const src = fs.readFileSync(p, "utf8");
    assert.match(src, /SAATHIOS_PRIVATE_ALPHA_BROWSER_CERT_PASSED/);
    assert.match(src, /production_authorized: false/);
    assert.match(src, /127\.0\.0\.1/);
  });
});
