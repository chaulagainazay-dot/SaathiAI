import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  SAFE_REDIRECTS,
  NEVER_REDIRECT_SOURCES,
  validateRedirectTable,
  toNextRedirects,
} from "./redirects.js";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

describe("M47.5 safe redirects", () => {
  it("validates without errors", () => {
    assert.deepEqual(validateRedirectTable(), []);
  });

  it("only infrastructure and me are soft-redirected", () => {
    const sources = SAFE_REDIRECTS.map((r) => r.source).sort();
    assert.deepEqual(sources, ["/infrastructure", "/me"].sort());
    assert.ok(SAFE_REDIRECTS.every((r) => r.permanent === false));
  });

  it("never redirects forbidden paths", () => {
    for (const n of NEVER_REDIRECT_SOURCES) {
      assert.ok(!SAFE_REDIRECTS.some((r) => r.source === n || r.source.startsWith(n + "/")));
    }
  });

  it("toNextRedirects shape for next.config", () => {
    const n = toNextRedirects();
    assert.ok(n.every((r) => r.source && r.destination && r.permanent === false));
  });

  it("next.config imports redirects module", () => {
    const src = readFileSync(join(root, "next.config.mjs"), "utf8");
    assert.match(src, /toNextRedirects|redirects/);
  });

  it("page-level redirects exist for infrastructure and me", () => {
    const infra = readFileSync(join(root, "app/infrastructure/page.jsx"), "utf8");
    const me = readFileSync(join(root, "app/me/page.jsx"), "utf8");
    assert.match(infra, /redirect\(/);
    assert.match(infra, /\/monitoring/);
    assert.match(me, /redirect\(/);
    assert.match(me, /\/settings/);
  });

  it("monitoring includes infra workspace", () => {
    const mon = readFileSync(join(root, "app/monitoring/page.jsx"), "utf8");
    assert.match(mon, /InfraHealthWorkspace/);
  });

  it("settings includes profile MobileMe", () => {
    const set = readFileSync(join(root, "app/settings/page.jsx"), "utf8");
    assert.match(set, /MobileMe/);
  });
});
