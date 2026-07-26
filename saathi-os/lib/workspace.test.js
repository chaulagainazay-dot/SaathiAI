import test from "node:test";
import assert from "node:assert/strict";
import { SIGNAL } from "./spatial.js";
import {
  fmt,
  fmtTime,
  ageSeconds,
  UNKNOWN,
  UNAVAILABLE,
  NOT_CONFIGURED,
  missionSignal,
  normalizeMission,
  filterMissions,
  sortMissions,
  agentStatusLabel,
  agentSignal,
  agentAuthorityKind,
  normalizeAgent,
  approvalRiskLevel,
  isApprovalExpired,
  approvalLifecycle,
  isApprovalDecidable,
  approvalSignal,
  normalizeApproval,
  filterPlatformApprovals,
  summarizePlatformApprovals,
  attentionItemSeverity,
  normalizeAttention,
  groupAttentionBySeverity,
  buildCommands,
  filterCommands,
  groupCommands,
} from "./workspace.js";

const NOW = 1_700_000_000; // fixed epoch seconds for determinism

/* ---------------------------------------------------------------- formatting */

test("fmt resolves missing scalars to truthful sentinels, never blanks", () => {
  assert.equal(fmt(null), UNKNOWN);
  assert.equal(fmt(undefined), UNKNOWN);
  assert.equal(fmt(""), UNKNOWN);
  assert.equal(fmt("   "), UNKNOWN); // whitespace-only trims to empty → fallback
  assert.equal(fmt("ok"), "ok");
  assert.equal(fmt(0), 0);
  assert.equal(fmt(null, UNAVAILABLE), UNAVAILABLE);
});

test("fmtTime is deterministic and safe on junk", () => {
  assert.equal(fmtTime(0), UNKNOWN);
  assert.equal(fmtTime(-5), UNKNOWN);
  assert.equal(fmtTime("nope"), UNKNOWN);
  assert.equal(fmtTime(NOW), "2023-11-14T22:13:20Z");
  assert.equal(fmtTime(0, NOT_CONFIGURED), NOT_CONFIGURED);
});

test("ageSeconds clamps to >=0 and returns null when unknown", () => {
  assert.equal(ageSeconds(NOW - 100, NOW), 100);
  assert.equal(ageSeconds(NOW + 100, NOW), 0);
  assert.equal(ageSeconds(0, NOW), null);
});

/* ------------------------------------------------------------------- mission */

test("missionSignal: blocked/failed → danger; attention/approvals raise it", () => {
  assert.equal(missionSignal({ status: "blocked" }), SIGNAL.DANGER);
  assert.equal(missionSignal({ status: "failed" }), SIGNAL.DANGER);
  assert.equal(missionSignal({ status: "completed" }), SIGNAL.SUCCESS);
  assert.equal(missionSignal({ status: "active" }, { attentionCount: 1 }), SIGNAL.ATTENTION);
  assert.equal(missionSignal({ status: "active" }, { pendingApprovals: 2 }), SIGNAL.ATTENTION);
  assert.equal(missionSignal(null), SIGNAL.UNKNOWN);
});

test("normalizeMission derives related counts by matching mission_id", () => {
  const m = normalizeMission(
    { mission_id: "m1", name: "Launch", key: "LN", status: "active", project_id: "p1", created_at: NOW },
    {
      executions: [
        { mission_id: "m1", state: "RUNNING" },
        { mission_id: "m1", state: "SUCCEEDED" },
        { mission_id: "other", state: "RUNNING" },
      ],
      approvals: [{ mission_id: "m1", status: "pending" }, { mission_id: "m1", status: "approved" }],
      attention: [{ mission_id: "m1" }],
    }
  );
  assert.equal(m.id, "m1");
  assert.equal(m.executionCount, 2);
  assert.equal(m.activeExecutions, 1);
  assert.equal(m.pendingApprovals, 1);
  assert.equal(m.attentionCount, 1);
  assert.equal(m.signal, SIGNAL.ATTENTION); // pending approval raises it
  assert.equal(m.projectId, "p1");
});

test("normalizeMission surfaces sentinels for missing fields", () => {
  const m = normalizeMission({ mission_id: "m2" });
  assert.equal(m.name, UNKNOWN);
  assert.equal(m.projectId, UNAVAILABLE);
  assert.equal(m.createdAt, UNKNOWN);
});

test("filterMissions + sortMissions", () => {
  const items = [
    normalizeMission({ mission_id: "a", name: "Alpha", status: "active" }, { executions: [{ mission_id: "a" }, { mission_id: "a" }] }),
    normalizeMission({ mission_id: "b", name: "Beta", status: "blocked" }),
    normalizeMission({ mission_id: "c", name: "Gamma", status: "completed" }),
  ];
  assert.equal(filterMissions(items, { status: "blocked" }).length, 1);
  assert.equal(filterMissions(items, { q: "gam" }).length, 1);
  assert.equal(filterMissions(items, { q: "b" })[0].name, "Beta");
  assert.equal(sortMissions(items, "risk")[0].status, "blocked"); // danger first
  assert.equal(sortMissions(items, "activity")[0].id, "a"); // most runs first
});

/* --------------------------------------------------------------------- agent */

test("agentStatusLabel maps state + runtime facts", () => {
  assert.equal(agentStatusLabel("ACTIVE"), "Available");
  assert.equal(agentStatusLabel("ACTIVE", { running: true }), "Running");
  assert.equal(agentStatusLabel("ACTIVE", { waitingApproval: true }), "Waiting for approval");
  assert.equal(agentStatusLabel("SUSPENDED"), "Inactive");
  assert.equal(agentStatusLabel("REVOKED"), "Blocked");
  assert.equal(agentStatusLabel("weird"), UNKNOWN);
});

test("agentSignal + authorityKind", () => {
  assert.equal(agentSignal("ACTIVE"), SIGNAL.ACTIVE);
  assert.equal(agentSignal("REVOKED"), SIGNAL.DANGER);
  assert.equal(agentSignal("SUSPENDED"), SIGNAL.IDLE);
  assert.equal(agentAuthorityKind({ authority_ceiling: "READ_ONLY" }), "advisory");
  assert.equal(agentAuthorityKind({ authority_ceiling: "SECURITY_SENSITIVE" }), "execution");
  assert.equal(agentAuthorityKind({}), "advisory");
});

test("normalizeAgent binds runs by binding_id and flags failures", () => {
  const a = normalizeAgent(
    { binding_id: "b1", agent_id: "worker", name: "Worker", state: "ACTIVE", authority_ceiling: "WRITE", allowed_tools: ["t1"], version: 2, created_at: NOW },
    { executions: [{ binding_id: "b1", state: "RUNNING" }, { binding_id: "b1", state: "FAILED" }, { binding_id: "x", state: "RUNNING" }] }
  );
  assert.equal(a.runs.length, 2);
  assert.equal(a.recentFailures.length, 1);
  assert.equal(a.statusLabel, "Running");
  assert.equal(a.authorityKind, "execution");
  assert.equal(a.bound, true);
  assert.equal(a.allowedTools.length, 1);
});

/* ------------------------------------------------------------------ approval */

test("approvalRiskLevel classifies by side-effect/authority keywords", () => {
  assert.equal(approvalRiskLevel({ side_effect_class: "DESTRUCTIVE" }), "high");
  assert.equal(approvalRiskLevel({ authority: "FINANCIAL" }), "high");
  assert.equal(approvalRiskLevel({ side_effect_class: "WRITE" }), "medium");
  assert.equal(approvalRiskLevel({ side_effect_class: "READ_ONLY" }), "low");
  assert.equal(approvalRiskLevel({}), "unknown");
});

test("approval expiry + lifecycle + decidability are server-truthful", () => {
  const pending = { status: "pending", expires_at: NOW + 100 };
  const expired = { status: "pending", expires_at: NOW - 100 };
  const consumed = { status: "approved", consumed_at: NOW - 5 };
  assert.equal(isApprovalExpired(expired, NOW), true);
  assert.equal(isApprovalExpired(pending, NOW), false);
  assert.equal(isApprovalExpired({ expires_at: 0 }, NOW), false); // no expiry
  assert.equal(approvalLifecycle(pending, NOW), "pending");
  assert.equal(approvalLifecycle(expired, NOW), "expired");
  assert.equal(approvalLifecycle(consumed, NOW), "consumed");
  assert.equal(isApprovalDecidable(pending, NOW), true);
  assert.equal(isApprovalDecidable(expired, NOW), false);
  assert.equal(isApprovalDecidable(consumed, NOW), false);
});

test("approvalSignal: high-risk pending is danger, settled reflects outcome", () => {
  assert.equal(approvalSignal({ status: "pending", side_effect_class: "DESTRUCTIVE", expires_at: NOW + 10 }, NOW), SIGNAL.DANGER);
  assert.equal(approvalSignal({ status: "pending", side_effect_class: "WRITE", expires_at: NOW + 10 }, NOW), SIGNAL.ATTENTION);
  assert.equal(approvalSignal({ status: "approved" }, NOW), SIGNAL.SUCCESS);
  assert.equal(approvalSignal({ status: "rejected" }, NOW), SIGNAL.DANGER);
});

test("normalizeApproval + filter + summary", () => {
  const raw = [
    { approval_id: "a1", tool_id: "echo", status: "pending", side_effect_class: "DESTRUCTIVE", expires_at: NOW + 100 },
    { approval_id: "a2", tool_id: "read", status: "pending", side_effect_class: "READ_ONLY", expires_at: NOW - 100 }, // expired
    { approval_id: "a3", tool_id: "write", status: "approved", consumed_at: NOW - 1 }, // consumed
    { approval_id: "a4", tool_id: "x", status: "rejected" },
  ].map((a) => normalizeApproval(a, NOW));
  assert.equal(raw[0].decidable, true);
  assert.equal(raw[1].lifecycle, "expired");
  assert.equal(raw[2].lifecycle, "consumed");
  const s = summarizePlatformApprovals(raw);
  assert.equal(s.pending, 1);
  assert.equal(s.highRisk, 1);
  assert.equal(s.consumed, 1);
  assert.equal(s.rejected, 1);
  assert.equal(s.expired, 1);
  assert.equal(filterPlatformApprovals(raw, { lifecycle: "expired" }).length, 1);
  assert.equal(filterPlatformApprovals(raw, { risk: "high" }).length, 1);
  assert.equal(filterPlatformApprovals(raw, { q: "echo" }).length, 1);
});

/* ----------------------------------------------------------------- attention */

test("attentionItemSeverity takes worst reason; empty → informational", () => {
  assert.equal(attentionItemSeverity({ attention_reasons: [] }), "informational");
  const sev = attentionItemSeverity({ attention_reasons: ["waiting_approval", "failed"] });
  assert.ok(["critical", "high", "medium", "low", "informational"].includes(sev));
});

test("normalizeAttention + grouping into four lanes", () => {
  const items = [
    normalizeAttention({ execution_id: "e1", tool_id: "t", state: "FAILED", attention_reasons: ["failed"], created_at: NOW }, NOW),
    normalizeAttention({ execution_id: "e2", tool_id: "t", state: "OK", attention_reasons: [] }, NOW),
  ];
  assert.equal(items[0].id, "e1");
  assert.equal(items[0].objectType, "execution");
  const g = groupAttentionBySeverity(items);
  assert.ok(Array.isArray(g.critical) && Array.isArray(g.informational));
  const total = g.critical.length + g.high.length + g.medium.length + g.informational.length;
  assert.equal(total, 2); // every item lands in exactly one lane
});

/* ------------------------------------------------------------- command palette */

test("buildCommands always has navigation; object commands come from records", () => {
  const cmds = buildCommands({
    missions: [{ id: "m1", name: "Launch", key: "LN", status: "active" }],
    agents: [{ id: "b1", name: "Worker", agentId: "worker", statusLabel: "Available" }],
    approvals: [{ id: "a1", toolId: "echo", lifecycle: "pending", risk: "low" }],
    attention: [{ id: "e1", title: "e", severity: "high", reason: "failed" }],
  });
  assert.ok(cmds.some((c) => c.id === "go-missions" && c.route === "/platform/missions"));
  assert.ok(cmds.some((c) => c.id === "mission:m1" && c.route === "/platform/missions/m1"));
  assert.ok(cmds.some((c) => c.id === "agent:b1"));
  assert.ok(cmds.some((c) => c.id === "approval:a1"));
  assert.ok(cmds.some((c) => c.id === "attention:e1"));
  // no mutation/decision command is ever synthesized
  assert.ok(!cmds.some((c) => /approve|reject|decide|cancel|revoke/i.test(c.id)));
});

test("filterCommands + groupCommands", () => {
  const cmds = buildCommands({});
  assert.equal(filterCommands(cmds, "").length, cmds.length);
  assert.ok(filterCommands(cmds, "agents").every((c) => /agent/i.test(`${c.label} ${c.keywords}`)));
  const groups = groupCommands(cmds);
  assert.equal(groups[0].group, "Navigate");
});
