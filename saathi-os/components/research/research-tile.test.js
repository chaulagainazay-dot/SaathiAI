// Static checks on the Research Intelligence tile (Phase 34): read-only presentation,
// same-origin fetch, product states, no trade controls/wording.
import { test } from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import path from "node:path";

const dir = path.dirname(new URL(import.meta.url).pathname);
const jsx = fs.readFileSync(path.join(dir, "ResearchIntelligence.jsx"), "utf8");
const css = fs.readFileSync(path.join(dir, "../../app/research/research.css"), "utf8");
const page = fs.readFileSync(path.join(dir, "../../app/research/page.jsx"), "utf8");

test("tile fetches the research API via same-origin API_BASE (no :8765)", () => {
  assert.ok(jsx.includes("/api/v1/research"), "must call research API");
  assert.ok(jsx.includes("API_BASE") && jsx.includes("afetch"), "must use afetch + API_BASE");
  assert.ok(!jsx.includes("8765"), "must not hardcode backend port");
  assert.ok(!/https?:\/\/localhost/.test(jsx), "must not hardcode an absolute origin");
});

test("renders LOADING / EMPTY / ERROR / DEGRADED product states", () => {
  for (const s of ["LOADING", "EMPTY", "ERROR", "DEGRADED"]) {
    assert.ok(jsx.includes(`"${s}"`), `missing state ${s}`);
  }
  assert.ok(/loading/i.test(jsx) && /Unable to retrieve/i.test(jsx));
  assert.ok(/No supported research evidence/i.test(jsx));
});

test("no Buy/Sell/trade controls or trade-score wording", () => {
  const low = (jsx + css).toLowerCase();
  for (const banned of ["buy", "sell", "trade_score", "buy_score", "alpha_score",
                        "position size", "target price", "place order"]) {
    assert.ok(!low.includes(banned), `forbidden term present: ${banned}`);
  }
});

test("surfaces evidence, source health, and token-gated document state", () => {
  assert.ok(jsx.includes("evidence"), "evidence must be shown");
  assert.ok(jsx.includes("source_health") || jsx.includes("Source health"));
  assert.ok(jsx.includes("token_gated_note"), "token-gated doc state surfaced");
});

test("accessible + responsive (aria labels, focus, no color-only health, media query)", () => {
  assert.ok(jsx.includes("aria-label") && jsx.includes("aria-busy") && jsx.includes("role="));
  assert.ok(css.includes(":focus-visible"), "focus states present");
  assert.ok(css.includes("@media"), "responsive breakpoint present");
  assert.ok(jsx.includes("ri-stat"), "health has a text label, not color only");
});

test("page route renders the tile", () => {
  assert.ok(page.includes("ResearchIntelligence"));
});
