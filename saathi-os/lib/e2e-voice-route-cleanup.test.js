// Regression tests for the SaathiOS full end-to-end functional audit.
//
// DEFECT-003 / DEFECT-004: Shell mounts VoiceOutputProvider and
// VoiceRuntimeProvider ABOVE the router children, so neither unmounts on a
// client-side navigation. The existing unmount cleanup therefore never ran on a
// route change: assistant audio (a detached Audio element) kept playing on an
// unrelated page, and the microphone MediaStream stayed hot after navigating
// away from the voice surface.
//
// These are source-contract tests in the same style as lib/ielts.test.js. They
// pin the wiring, not the runtime behaviour; audible/observable confirmation is
// covered by the browser certification journey and the owner audio checklist.
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const outputProvider = readFileSync(
  new URL("../components/voice/VoiceOutputProvider.jsx", import.meta.url),
  "utf8"
);
const runtimeProvider = readFileSync(
  new URL("../components/voice/VoiceRuntimeProvider.jsx", import.meta.url),
  "utf8"
);
const shell = readFileSync(
  new URL("../components/Shell.jsx", import.meta.url),
  "utf8"
);

describe("voice providers clean up on route change", () => {
  it("Shell still mounts both providers above the routed children", () => {
    // If this ever stops being true the route-change effects below become
    // redundant rather than wrong — but the assumption must stay explicit.
    const outputAt = shell.indexOf("<VoiceOutputProvider>");
    const runtimeAt = shell.indexOf("<VoiceRuntimeProvider>");
    const childrenAt = shell.indexOf("<ShellInner>{children}</ShellInner>");
    assert.ok(outputAt > -1 && runtimeAt > -1 && childrenAt > -1);
    assert.ok(outputAt < childrenAt, "VoiceOutputProvider wraps the routed children");
    assert.ok(runtimeAt < childrenAt, "VoiceRuntimeProvider wraps the routed children");
  });

  it("VoiceOutputProvider stops speech when the pathname changes", () => {
    assert.ok(
      outputProvider.includes('import { usePathname } from "next/navigation"'),
      "must observe the route"
    );
    assert.ok(outputProvider.includes("const pathname = usePathname()"));
    assert.ok(
      outputProvider.includes("if (spokenPathRef.current === pathname) return;"),
      "must not cancel on first render"
    );
    assert.ok(
      /spokenPathRef\.current = pathname;\s*\n\s*stop\(\);/.test(outputProvider),
      "must call stop() after recording the new path"
    );
    assert.ok(
      /}, \[pathname, stop\]\);/.test(outputProvider),
      "effect must depend on pathname and stop"
    );
  });

  it("VoiceRuntimeProvider releases the microphone when the pathname changes", () => {
    assert.ok(
      runtimeProvider.includes('import { usePathname } from "next/navigation"'),
      "must observe the route"
    );
    assert.ok(runtimeProvider.includes("const pathname = usePathname()"));
    assert.ok(
      runtimeProvider.includes("if (listeningPathRef.current === pathname) return;"),
      "must not reset on first render"
    );
    assert.ok(
      /listeningPathRef\.current = pathname;\s*\n\s*hardReset\(\);/.test(runtimeProvider),
      "must call hardReset() after recording the new path"
    );
    assert.ok(
      /}, \[pathname, hardReset\]\);/.test(runtimeProvider),
      "effect must depend on pathname and hardReset"
    );
  });

  it("hardReset actually stops recognition and releases every media track", () => {
    assert.ok(runtimeProvider.includes("recognitionRef.current?.stop?.()"));
    assert.ok(
      runtimeProvider.includes(
        "mediaStreamRef.current.getTracks().forEach((track) => track.stop())"
      ),
      "microphone tracks must be stopped, not just dereferenced"
    );
    assert.ok(runtimeProvider.includes("mediaStreamRef.current = null;"));
  });

  it("stop() tears down local audio and cancels the server-side operation", () => {
    assert.ok(outputProvider.includes("clearLocalAudio();"));
    assert.ok(
      outputProvider.includes("voiceActions.cancel(operation.operationId, token)"),
      "an in-flight server speech operation must be cancelled, not orphaned"
    );
    assert.ok(outputProvider.includes('dispatch({ type: "CANCELLED" });'));
  });

  it("logout / context switch still resets both providers", () => {
    // PLATFORM_CONTEXT_EVENT fires on login, logout and workspace switch.
    assert.ok(outputProvider.includes("window.addEventListener(PLATFORM_CONTEXT_EVENT, onContext)"));
    assert.ok(outputProvider.includes("clearLocalAudio();"));
    assert.ok(runtimeProvider.includes("window.addEventListener(PLATFORM_CONTEXT_EVENT, onContext)"));
    assert.ok(runtimeProvider.includes("hardReset();"));
  });

  it("speak() cancels any prior operation before starting a new one", () => {
    // Prevents two assistant responses speaking at once.
    assert.ok(
      /const approvedText = String\(text \|\| ""\)\.trim\(\);[\s\S]{0,200}await stop\(\);/.test(
        outputProvider
      ),
      "speak() must await stop() before issuing a new synthesis request"
    );
  });
});
