import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const HYBRID = new URL("../app/command/command-hybrid.css", import.meta.url);
const GLOBALS = new URL("../app/globals.css", import.meta.url);

const hybrid = fs.readFileSync(HYBRID, "utf8");
const globals = fs.readFileSync(GLOBALS, "utf8");

/** The `@media (<query>)` block containing `must`, or the first such block. */
function mediaBlock(css, query, must = "") {
  let start = -1, from = 0;
  while (true) {
    const i = css.indexOf(`@media (${query})`, from);
    if (i < 0) break;
    if (!must) { start = i; break; }
    const body = blockAt(css, i);
    if (body && body.includes(must)) { start = i; break; }
    from = i + 1;
  }
  if (start < 0) return null;
  return blockAt(css, start);
}

function blockAt(css, start) {
  let depth = 0, i = css.indexOf("{", start);
  const from = i;
  for (; i < css.length; i++) {
    if (css[i] === "{") depth++;
    else if (css[i] === "}") { depth--; if (depth === 0) return css.slice(from, i + 1); }
  }
  return null;
}

/** The declaration body of the first `selector { ... }` rule at top level. */
function rule(css, selector) {
  const re = new RegExp(`(^|[},])\\s*${selector.replace(/[.*+?^${}()|[\\]\\\\]/g, "\\\\$&")}\\s*\\{([^}]*)\\}`, "m");
  const m = css.match(re);
  return m ? m[2] : null;
}

// ── grid overflow (defect 1) ───────────────────────────────────────────────

test("the stacked command grid track carries no automatic minimum", () => {
  // `1fr` is `minmax(auto, 1fr)`, and that automatic minimum is the widest
  // item's min-content -- which is how one column resolved to 438px inside a
  // 354px grid at 390px. Measured before and after in Phase 8A.
  const block = mediaBlock(hybrid, "max-width: 1180px");
  assert.ok(block, "the command shell must define a stacking breakpoint");
  assert.match(block, /grid-template-columns:\s*minmax\(0,\s*1fr\)/,
    "the stacked track must be minmax(0, 1fr), never a bare 1fr");
  assert.ok(!/grid-template-columns:\s*1fr\s*;/.test(block),
    "a bare `1fr` reintroduces the min-content floor");
});

test("grid items are allowed to shrink below their intrinsic width", () => {
  const grid = rule(hybrid, "\\.dl-grid,\\s*\\n\\.dl-grid > \\*") || hybrid;
  assert.match(hybrid, /\.dl-grid,\s*\.dl-grid > \*\s*\{[^}]*min-width:\s*0/s,
    "both the grid and its items need min-width: 0");
});

test("the composer can wrap and its input can shrink", () => {
  // A flex <input> keeps a ~182px automatic minimum; with the row unable to
  // wrap, the composer's min-content was the 438px that set the whole track.
  assert.match(hybrid, /\.dl-composer\s*\{[^}]*flex-wrap:\s*wrap/s);
  assert.match(hybrid, /\.dl-composer \.dl-input\s*\{[^}]*min-width:\s*0/s);
});

test("overflow is never hidden to mask the grid defect", () => {
  const phase8a = hybrid
    .slice(hybrid.lastIndexOf("/*", hybrid.indexOf("Phase 8A: responsive command shell")))
    .replace(/\/\*[\s\S]*?\*\//g, "");   // the prose explains why it is absent
  assert.ok(!/overflow-x:\s*hidden/.test(phase8a),
    "clipping would conceal the defect rather than remove it");
});

test("the stack begins before the centre column can be squeezed", () => {
  // The three-column layout pins 220px + 240px of side columns, so below about
  // 1180px the only track that could yield was the centre one -- measured
  // collapsing to 81px at 901px while the sides kept full width.
  assert.ok(hybrid.includes("@media (max-width: 1180px)"),
    "stacking must start at 1180px, not 900px");
  const desktop = rule(hybrid, "\\.dl-layout-c");
  assert.match(desktop, /220px\s+minmax\(0,\s*1\.2fr\)\s+240px/,
    "the desktop three-column layout is unchanged above the breakpoint");
});

// ── fixed-layer occlusion (defect 2) ───────────────────────────────────────

test("the command shell reserves space for fixed bottom chrome", () => {
  const block = mediaBlock(hybrid, "max-width: 900px");
  assert.ok(block, "a mobile block must exist");
  assert.match(block, /\.hc-root\s*\{[^}]*padding-bottom:\s*calc\([^)]*env\(safe-area-inset-bottom/s,
    "the reservation must follow the existing safe-area convention");
});

test("the voice dock leaves fixed positioning at narrow width", () => {
  const block = mediaBlock(globals, "max-width: 820px", ".voice-output-dock");
  assert.ok(block, "the dock must have a narrow-width block");
  assert.match(block, /\.voice-output-dock\s*\{[^}]*position:\s*static/s,
    "a fixed dock covering 340px of a 390px viewport is the occlusion");
  assert.ok(!/\.voice-output-dock\s*\{[^}]*position:\s*fixed/s.test(block),
    "the narrow-width dock must not stay fixed");
});

test("the dock keeps its desktop behaviour", () => {
  assert.match(globals, /\.voice-output-dock\s*\{[^}]*position:\s*fixed/s,
    "the base rule is unchanged; only the narrow-width override differs");
});

// ── voice ownership must be untouched by layout work ───────────────────────

test("responsive work introduces no second voice surface", () => {
  // Layout may move the dock; it may never clone it. One dock component, one
  // mount site, and no capture API anywhere in the stylesheets.
  const dockSrc = fs.readFileSync(
    new URL("../components/voice/VoiceOutputDock.jsx", import.meta.url), "utf8");
  assert.ok(!/getUserMedia|new AudioContext|SpeechRecognition/.test(dockSrc),
    "the dock must not own capture");

  const shell = fs.readFileSync(new URL("../components/Shell.jsx", import.meta.url), "utf8");
  const mounts = (shell.match(/<VoiceOutputDock\b/g) || []).length;
  assert.equal(mounts, 1, "exactly one dock mount site");

  for (const css of [hybrid, globals]) {
    assert.ok(!/getUserMedia|VoiceRuntimeProvider/.test(css),
      "stylesheets must not reference voice runtime internals");
  }
});

test("the responsive fix is CSS-only -- no resize listeners were added", () => {
  const page = fs.readFileSync(new URL("../app/command/page.jsx", import.meta.url), "utf8");
  const code = page.replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, "");
  // matchMedia is fine and pre-existing (reduced-motion); a resize loop is not.
  for (const banned of ["ResizeObserver", 'addEventListener("resize"',
    "addEventListener('resize'"]) {
    assert.ok(!code.includes(banned), `${banned} must not drive layout`);
  }
});

// ── frozen surfaces must survive the layout change ─────────────────────────

test("frozen panel semantics remain present", () => {
  const page = fs.readFileSync(new URL("../app/command/page.jsx", import.meta.url), "utf8");
  assert.match(page, /<WhatNeedsYou model=\{attention\} \/>/, "Phase 7 surface still mounted");
  assert.match(page, /<WhoIsWorking model=\{orchestration\} \/>/, "Phase 6 surface still mounted");
  assert.match(page, /useCommandCoreSnapshot\(/, "Phase 5 snapshot still owned here");
});

test("panels that must shrink declare min-width: 0", () => {
  const wny = fs.readFileSync(
    new URL("../components/command/WhatNeedsYou.jsx", import.meta.url), "utf8");
  const wiw = fs.readFileSync(
    new URL("../components/command/WhoIsWorking.jsx", import.meta.url), "utf8");
  assert.match(wny, /\.wny\s*\{[^}]*min-width:\s*0/s);
  assert.match(wiw, /\.wiw\s*\{[^}]*min-width:\s*0/s);
});
