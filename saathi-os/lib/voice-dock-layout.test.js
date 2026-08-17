/**
 * R2.1-D1 regression: the live-voice runtime dock must stay reachable.
 *
 * The defect this guards: the dock rendered in normal document flow as the last
 * sibling of <main>, so on desktop it sat underneath the fixed sidebar and the
 * fixed status bar (its mic was not the hit-test target), and on phones it fell
 * past the bottom of a non-scrolling viewport entirely.
 *
 * This file asserts the layout contract in the component source. Real geometry
 * at real viewports is certified in the browser by
 * saathi-os/scripts/r21_voice_dock_layout_cert.mjs.
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const SOURCE = readFileSync(
  join(HERE, "..", "components", "voice", "VoiceRuntimeDock.jsx"),
  "utf8"
);

/** The declaration block of a selector, as authored. */
function block(selector) {
  const start = SOURCE.indexOf(`${selector} {`);
  assert.notEqual(start, -1, `missing rule for ${selector}`);
  const end = SOURCE.indexOf("}", start);
  assert.notEqual(end, -1, `unterminated rule for ${selector}`);
  return SOURCE.slice(start, end);
}

/** The body of a media query, as authored. */
function media(query) {
  const start = SOURCE.indexOf(`@media ${query} {`);
  assert.notEqual(start, -1, `missing media query ${query}`);
  const end = SOURCE.indexOf("\n        }", start);
  assert.notEqual(end, -1, `unterminated media query ${query}`);
  return SOURCE.slice(start, end);
}

describe("voice runtime dock layout (R2.1-D1)", () => {
  const base = block(".voice-runtime-dock");

  it("is shell chrome, not document flow", () => {
    assert.match(base, /position:\s*fixed/);
    assert.match(base, /margin:\s*0/);
    assert.doesNotMatch(base, /margin:\s*\d+px\s+\d+px/);
  });

  it("anchors bottom-left", () => {
    assert.match(base, /left:\s*calc\(/);
    assert.match(base, /bottom:\s*calc\(/);
    assert.doesNotMatch(base, /\n\s+right:/);
    assert.doesNotMatch(base, /\n\s+top:/);
  });

  it("clears the primary navigation sidebar", () => {
    assert.match(base, /left:\s*calc\(var\(--shell-sidebar-expanded[^)]*\)\s*\+/);
    const collapsed = block(
      ':global(.shell-desktop[data-sidebar="collapsed"]) ~ .voice-runtime-dock'
    );
    assert.match(collapsed, /left:\s*calc\(var\(--shell-sidebar-collapsed[^)]*\)\s*\+/);
  });

  it("sits above the fixed bottom status bar", () => {
    assert.match(base, /bottom:\s*calc\(var\(--shell-statusbar-h[^)]*\)\s*\+\s*\d+px/);
    // Above the status bar (z-index 42) but under the M75 output dock (48).
    const zIndex = Number(/z-index:\s*(\d+)/.exec(base)?.[1]);
    assert.ok(zIndex > 42 && zIndex < 48, `z-index ${zIndex} outside shell range`);
  });

  it("cannot introduce horizontal overflow", () => {
    assert.match(base, /width:\s*min\(\s*360px,\s*calc\(100vw\s*-\s*\d+px\)\s*\)/);
  });

  it("bounds its own height instead of growing off-screen", () => {
    assert.match(base, /max-height:\s*min\(/);
    assert.match(base, /overflow-y:\s*auto/);
  });

  it("stacks clear of the bottom-right output dock on narrow viewports", () => {
    // Output dock: fixed bottom 42px (globals.css), re-anchored to 76px <=820px.
    const narrow = media("(max-width: 1023px)");
    const reanchored = media("(max-width: 820px)");
    const reserve = (css) => Number(/\+\s*(\d+)px\)/.exec(css)?.[1]);
    assert.ok(reserve(narrow) >= 200, "narrow reserve too small for the output dock");
    assert.ok(
      reserve(reanchored) >= reserve(narrow) + 34,
      "reserve must grow with the output dock re-anchor at 820px"
    );
  });

  it("re-anchors on the phone companion, which has no sidebar or status bar", () => {
    const phone = media("(max-width: 699px)");
    assert.match(phone, /left:\s*10px/);
    assert.match(phone, /width:\s*min\(360px,\s*calc\(100vw\s*-\s*20px\)\)/);
    assert.match(phone, /bottom:\s*calc\(\d+px\s*\+\s*env\(safe-area-inset-bottom/);
  });

  it("keeps the mic an adequate touch target", () => {
    const mic = block(".voice-runtime-mic");
    assert.match(mic, /min-width:\s*44px/);
    assert.match(mic, /min-height:\s*44px/);
  });

  it("keeps keyboard focus visible on every dock control", () => {
    const focus = block(
      ".voice-runtime-mic:focus-visible,\n        .voice-runtime-interrupt:focus-visible,\n        .voice-runtime-retry:focus-visible"
    );
    assert.match(focus, /outline:\s*2px solid/);
    assert.match(focus, /outline-offset/);
  });

  it("keeps the mic accessibly named and keyboard operable", () => {
    assert.match(SOURCE, /className="voice-runtime-mic"/);
    assert.match(SOURCE, /aria-label=\{micLabel\}/);
    assert.match(SOURCE, /type="button"/);
  });
});
