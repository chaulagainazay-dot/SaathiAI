/**
 * SaathiOS Orbit — geometry, status mapping and token discipline.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

import {
  CORE_ID, RING_FRACTIONS, layoutOrbit, orbitEdges, orbitSummary,
  orbitTextSummary, statusToneFor, statusVar,
} from "./orbit.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");

const AGENTS = [
  { id: "a", label: "A", tier: 1, state: "active" },
  { id: "b", label: "B", tier: 1, state: "warning" },
  { id: "c", label: "C", tier: 2, state: "paused" },
  { id: "d", label: "D", tier: 2, state: "blocked" },
];

// ── status mapping ───────────────────────────────────────────────────────────────
test("status tones cover the real agent vocabulary", () => {
  assert.equal(statusToneFor("active"), "success");
  assert.equal(statusToneFor("healthy"), "success");
  assert.equal(statusToneFor("degraded"), "warning");
  assert.equal(statusToneFor("blocked"), "blocked");
  assert.equal(statusToneFor("failed"), "danger");
  assert.equal(statusToneFor("idle"), "paused");
  assert.equal(statusToneFor("pending"), "pending");
  assert.equal(statusToneFor("who-knows"), "neutral");
  assert.equal(statusToneFor(undefined), "neutral");
});

test("status always resolves to a semantic token, never a hex", () => {
  for (const s of ["active", "degraded", "blocked", "failed", "idle", "x"]) {
    const v = statusVar(statusToneFor(s));
    assert.match(v, /^var\(--status-[a-z]+\)$/);
  }
});

// ── layout ───────────────────────────────────────────────────────────────────────
test("layout places every agent and centres the core", () => {
  const l = layoutOrbit(AGENTS, { size: 800 });
  assert.equal(l.nodes.length, 4);
  assert.equal(l.core.x, 400);
  assert.equal(l.core.y, 400);
  assert.equal(l.core.id, CORE_ID);
});

test("tiers land on their own ring radius", () => {
  const l = layoutOrbit(AGENTS, { size: 800 });
  const t1 = l.nodes.filter((n) => n.tier === 1);
  const t2 = l.nodes.filter((n) => n.tier === 2);
  for (const n of t1) assert.equal(n.radius, 400 * RING_FRACTIONS[1]);
  for (const n of t2) assert.equal(n.radius, 400 * RING_FRACTIONS[2]);
  assert.ok(t2[0].radius > t1[0].radius, "tier 2 must orbit further out");
});

test("every node sits on its ring (distance from core == radius)", () => {
  const l = layoutOrbit(AGENTS, { size: 800 });
  for (const n of l.nodes) {
    const d = Math.hypot(n.x - l.core.x, n.y - l.core.y);
    assert.ok(Math.abs(d - n.radius) < 0.01, `${n.id} off its ring`);
  }
});

test("layout is deterministic — same input, same coordinates", () => {
  const a = layoutOrbit(AGENTS, { size: 800 });
  const b = layoutOrbit(AGENTS, { size: 800 });
  assert.deepEqual(a.nodes.map((n) => [n.id, n.x, n.y]), b.nodes.map((n) => [n.id, n.x, n.y]));
});

test("nodes on the same ring are evenly spaced", () => {
  const four = [1, 2, 3, 4].map((i) => ({ id: `n${i}`, label: `N${i}`, tier: 1, state: "active" }));
  const l = layoutOrbit(four, { size: 800 });
  const angles = l.nodes.map((n) => n.angle);
  assert.equal(angles[1] - angles[0], 90);
  assert.equal(angles[2] - angles[1], 90);
});

test("empty roster is valid, not a crash", () => {
  const l = layoutOrbit([], { size: 800 });
  assert.equal(l.nodes.length, 0);
  assert.equal(orbitEdges(l).length, 0);
});

// ── edges ────────────────────────────────────────────────────────────────────────
test("agents connect to the core by default", () => {
  const l = layoutOrbit(AGENTS, { size: 800 });
  const edges = orbitEdges(l);
  assert.equal(edges.length, 4);
  assert.ok(edges.every((e) => e.from === CORE_ID && e.kind === "core"));
});

test("reportsTo creates a peer edge instead of a core edge", () => {
  const withParent = [
    { id: "a", label: "A", tier: 1, state: "active" },
    { id: "b", label: "B", tier: 2, state: "active", reportsTo: "a" },
  ];
  const edges = orbitEdges(layoutOrbit(withParent, { size: 800 }));
  const peer = edges.find((e) => e.to === "b");
  assert.equal(peer.from, "a");
  assert.equal(peer.kind, "peer");
});

// ── summary ──────────────────────────────────────────────────────────────────────
test("summary counts and surfaces the WORST state, not an average", () => {
  const s = orbitSummary(AGENTS);
  assert.equal(s.total, 4);
  assert.equal(s.healthy, 1);
  assert.equal(s.attention, 2); // warning + blocked
  assert.equal(s.worst, "blocked");
});

test("a single danger outranks many healthy agents", () => {
  const s = orbitSummary([
    { id: "1", state: "active" }, { id: "2", state: "active" },
    { id: "3", state: "active" }, { id: "4", state: "failed" },
  ]);
  assert.equal(s.worst, "danger");
});

test("text summary is never empty (accessibility fallback)", () => {
  assert.match(orbitTextSummary(AGENTS), /4 agents in orbit/);
  assert.equal(orbitTextSummary([]), "No agents in orbit.");
});

// ── token discipline (the point of this component) ───────────────────────────────
const FILES = [
  "components/orbit/AgentOrbit.jsx",
  "app/orbit/page.jsx",
  "app/orbit/orbit.css",
  "lib/orbit.js",
];

test("all orbit files exist", () => {
  for (const f of FILES) assert.equal(existsSync(join(ROOT, f)), true, `missing ${f}`);
});

test("ZERO hardcoded hex colours — everything routes through tokens", () => {
  for (const f of FILES) {
    const src = readFileSync(join(ROOT, f), "utf8");
    const hex = src.match(/#[0-9a-fA-F]{6}\b/g) || [];
    assert.deepEqual(hex, [], `${f} contains hardcoded hex: ${hex.join(", ")}`);
  }
});

test("css defines the two new component tokens from existing primitives", () => {
  const css = readFileSync(join(ROOT, "app/orbit/orbit.css"), "utf8");
  assert.match(css, /--orbit-core:\s*var\(--color-amber-500\)/);
  assert.match(css, /--orbit-edge:\s*var\(--color-cyan-500\)/);
});

test("respects reduced motion", () => {
  const css = readFileSync(join(ROOT, "app/orbit/orbit.css"), "utf8");
  assert.match(css, /prefers-reduced-motion/);
});

test("constellation is accessible, not image-only", () => {
  const src = readFileSync(join(ROOT, "components/orbit/AgentOrbit.jsx"), "utf8");
  assert.match(src, /role="img"/);
  assert.match(src, /aria-label=\{text\}/);
  assert.match(src, /orbit-text-summary/);
  assert.match(src, /onKeyDown/);           // keyboard-selectable nodes
});

test("orbit surface claims no command authority", () => {
  const src = readFileSync(join(ROOT, "app/orbit/page.jsx"), "utf8");
  assert.match(src, /never commands/i);
  for (const banned of ["submitOrder", "executeAgent", "killAgent"]) {
    assert.ok(!src.includes(banned), `orbit must not expose ${banned}`);
  }
});
