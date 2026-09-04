import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const FRONTEND = join(dirname(fileURLToPath(import.meta.url)), "..");
const read = (relative) => readFileSync(join(FRONTEND, relative), "utf8");

describe("SaathiOS canonical root", () => {
  it("renders the mature Central Command component at /", () => {
    const root = read("app/page.jsx");
    assert.match(root, /import CommandCenterPage from "\.\/command\/page"/);
    assert.match(root, /<CommandCenterPage\s*\/>/);
    assert.match(root, /SaathiOS — Central Command/);
  });

  it("preserves the former attention dashboard at /home", () => {
    assert.equal(existsSync(join(FRONTEND, "app/home/page.jsx")), true);
    assert.match(read("app/home/page.jsx"), /export default function HomePage/);
  });

  it("publishes the SaathiOS product identity in root metadata", () => {
    const layout = read("app/layout.jsx");
    assert.match(layout, /title: "SaathiOS — Central Command"/);
    assert.match(layout, /powered by SaathiAI intelligence/);
    assert.doesNotMatch(layout, /SaathiAI — Sovereign Orbit/);
  });
});
