/**
 * The Live voice dock is `position: fixed`. Any page whose last element is
 * interactive will have that element sitting underneath it once the page is
 * scrolled to the end.
 *
 * That is not hypothetical: the calibration card was added at the bottom of the
 * diagnostics page, and `elementFromPoint` at the centre of its "Start
 * calibration" button resolved to the dock. A click there started Live Voice
 * instead — which is exactly what happened during a physical calibration
 * attempt, producing a runtime session and a microphone that stayed open,
 * blamed at the time on a broken auto-stop.
 *
 * The fix is scroll clearance, derived from the dock's own geometry. These tests
 * pin the contract; the geometry itself is verified in a real browser across the
 * viewport matrix, because a layout claim that is only checked against source
 * text is not a layout check.
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const CSS = readFileSync(join(HERE, "..", "..", "app", "globals.css"), "utf8");
const PAGE = readFileSync(
  join(HERE, "..", "..", "app", "settings", "voice", "diagnostics", "page.jsx"), "utf8");
const DOCK = readFileSync(
  join(HERE, "..", "..", "components", "voice", "VoiceRuntimeDock.jsx"), "utf8");
const PANEL = readFileSync(
  join(HERE, "..", "..", "components", "voice", "MicCalibrationPanel.jsx"), "utf8");

describe("the clearance token", () => {
  it("exists once, is named for what it is, and is derived from the dock", () => {
    assert.ok(CSS.includes("--voice-dock-clearance:"), "the token is defined");
    assert.equal(CSS.split("--voice-dock-clearance:").length - 1, 1, "defined exactly once");

    const decl = CSS.slice(CSS.indexOf("--voice-dock-clearance:"));
    const value = decl.slice(0, decl.indexOf(");") + 2);
    // Every term of the dock's own geometry, so the two cannot drift apart.
    assert.ok(value.includes("--voice-dock-offset"), "built on the dock's anchor");
    assert.ok(value.includes("min(46vh, 420px)"), "accounts for the dock's maximum height");
    const offsetDecl = CSS.slice(CSS.indexOf("--voice-dock-offset:"));
    assert.ok(offsetDecl.includes("env(safe-area-inset-bottom"), "accounts for the safe area");
    assert.ok(offsetDecl.includes("--shell-statusbar-h"), "accounts for the status band");
  });

  it("mirrors the dock's bottom anchor at every breakpoint", () => {
    // The dock re-anchors far above the viewport bottom on narrow layouts. A
    // clearance derived only from the desktop anchor left the control under the
    // dock at phone widths, which is where the layout is tightest.
    assert.ok(DOCK.includes("max-height: min(46vh, 420px)"));
    for (const [query, offset] of [
      [null, "+ 12px"],
      ["@media (max-width: 1023px)", "212px"],
      ["@media (max-width: 820px)", "246px"],
      ["@media (max-width: 699px)", "328px"],
    ]) {
      assert.ok(DOCK.includes(offset), "the dock still uses " + offset);
      assert.ok(CSS.includes(offset), "the clearance accounts for " + offset);
      if (query) assert.ok(CSS.includes(query), "clearance tracks " + query);
    }
    assert.ok(CSS.includes("--voice-dock-offset"), "the anchor is a named token");
  });

  it("leaves a focus-ring margin beyond the dock itself", () => {
    const decl = CSS.slice(CSS.indexOf("--voice-dock-clearance:"),
                           CSS.indexOf("--voice-dock-clearance:") + 400);
    assert.match(decl, /\+\s*24px/, "a visual/focus margin above the dock");
  });
});

describe("how the clearance is applied", () => {
  it("is a named opt-in rule, not a magic number in a component", () => {
    assert.ok(CSS.includes(".shell-page--dock-clearance { padding-bottom: var(--voice-dock-clearance); }"));
    assert.ok(PAGE.includes("shell-page--dock-clearance"), "the diagnostics page opts in");
    // The number must not be restated anywhere else.
    assert.ok(!PAGE.includes("46vh") && !PAGE.includes("420px"));
    assert.ok(!PANEL.includes("46vh") && !PANEL.includes("420px"));
  });

  it("uses padding, so the control stays in flow and keyboard order", () => {
    const rule = CSS.slice(CSS.indexOf(".shell-page--dock-clearance {"),
                           CSS.indexOf(".shell-page--dock-clearance {") + 120);
    assert.ok(rule.includes("padding-bottom"));
    for (const banned of ["position: absolute", "transform:", "margin-top: -"]) {
      assert.ok(!rule.includes(banned), banned);
    }
  });

  it("does not solve the overlap by any forbidden route", () => {
    // No z-index war, no pointer-events disabling, no shrinking, no moving the
    // dock, and no JavaScript viewport arithmetic in the calibration surface.
    assert.ok(!PANEL.includes("z-index"), "the button must not be stacked over the dock");
    assert.ok(!PANEL.includes("pointer-events"));
    assert.ok(!PANEL.includes("getBoundingClientRect"), "no JS viewport coordinates");
    assert.ok(!PANEL.includes("scrollIntoView"));
    assert.ok(!PAGE.includes("pointer-events"));
    assert.ok(!PAGE.includes("z-index"));
    // The dock's own anchoring is untouched by this change.
    assert.ok(DOCK.includes("z-index: 47;"));
  });

  it("introduces no horizontal overflow", () => {
    const rule = CSS.slice(CSS.indexOf(".shell-page--dock-clearance {"),
                           CSS.indexOf(".shell-page--dock-clearance {") + 120);
    assert.ok(!rule.includes("width:") && !rule.includes("padding-left") &&
              !rule.includes("padding-right"), "vertical clearance only");
  });

  it("keeps the calibration card last in the document", () => {
    // Allowed by the contract: sufficient scroll clearance makes it reachable.
    const diag = PAGE.indexOf("<VoiceDiagnosticsPanel");
    const cal = PAGE.indexOf("<MicCalibrationPanel");
    assert.ok(diag > -1 && cal > diag, "order preserved; clearance does the work");
  });
});
