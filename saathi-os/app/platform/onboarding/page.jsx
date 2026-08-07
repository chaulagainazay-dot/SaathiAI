"use client";
// M60 Workstream 1 — First-run onboarding. DERIVED read of real platform state +
// local-only progress. Safety steps require explicit acknowledgement and cannot
// be silently skipped. No unsupported backend mutation is performed.
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { SpatialWorkspaceShell } from "@/components/spatial/SpatialWorkspaceShell";
import { RequireSession } from "@/components/spatial/RequireSession";
import { WorkflowStepper } from "@/components/spatial/GuidedWorkflow";
import { SafetyBoundaryBadge } from "@/components/spatial/frame";
import { Field, SectionPanel } from "@/components/spatial/primitives";
import { usePlatformData, plat } from "@/lib/platform-client";
import { coreSignal } from "@/lib/spatial";
import { ONBOARDING_STEPS, onboardingProgress, onboardingFacts } from "@/lib/operator";
import { lsGet, lsSet, lsRemove, LS_KEYS } from "@/lib/local-store";

export default function OnboardingPage() {
  const d = usePlatformData();
  const router = useRouter();
  const [config, setConfig] = useState(null);
  const [completed, setCompleted] = useState([]);
  const [activeId, setActiveId] = useState("welcome");

  useEffect(() => { setCompleted(lsGet(LS_KEYS.onboarding, [])); }, []);
  useEffect(() => { if (d.token) plat("/config", { token: d.token }).then((r) => setConfig(r?.config || null)).catch(() => {}); }, [d.token]);

  const facts = useMemo(() => onboardingFacts({ health: d.health, me: d.me, config, diagnostics: d.diagnostics, projects: d.missions.length ? [] : [], bindings: d.bindings }), [d.health, d.me, config, d.diagnostics, d.bindings, d.missions]);
  const progress = useMemo(() => onboardingProgress(completed), [completed]);
  const cSignal = d.token ? coreSignal({ health: d.health, metrics: d.metrics, diagnostics: d.diagnostics }) : "unknown";
  const active = ONBOARDING_STEPS.find((s) => s.id === activeId) || ONBOARDING_STEPS[0];

  const markComplete = (id) => {
    const next = Array.from(new Set([...completed, id]));
    setCompleted(next);
    lsSet(LS_KEYS.onboarding, next);
    const idx = ONBOARDING_STEPS.findIndex((s) => s.id === id);
    if (idx < ONBOARDING_STEPS.length - 1) setActiveId(ONBOARDING_STEPS[idx + 1].id);
  };
  const restart = () => { setCompleted([]); lsRemove(LS_KEYS.onboarding); setActiveId("welcome"); };

  return (
    <SpatialWorkspaceShell
      title="First-run onboarding"
      subtitle="A guided, localhost-only walkthrough of your workspace, the safety boundaries, and the governed execution model. No production, connector, financial, or trading action is taken."
      breadcrumb={[{ label: "Home", href: "/platform" }, { label: "Onboarding" }]}
      signal={cSignal}
      health={d.health}
      loading={d.loading}
      error={d.error}
      paletteData={{}}
    >
      <RequireSession token={d.token} ready={d.ready}>
        <div style={{ display: "grid", gap: "var(--space-4)" }}>
          <WorkflowStepper steps={progress.steps} activeId={activeId} onSelect={setActiveId} />
          <div className="mono" style={{ fontSize: "var(--fs-2xs)", color: "var(--text-muted)" }}>
            Progress {progress.pct}% · safety acknowledged: {String(progress.safetyAcknowledged)} · stored locally only
          </div>

          <SectionPanel title={active.title} signal={active.safety ? "attention" : "active"}>
            {active.id === "welcome" && (
              <p style={{ color: "var(--text-secondary)" }}>Welcome to SaathiOS. This walkthrough explains what is safe to do on your machine and how governed execution works. You can skip educational steps, but safety steps must be acknowledged.</p>
            )}
            {active.id === "safety" && (
              <div style={{ display: "grid", gap: 10 }}>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <SafetyBoundaryBadge label="Localhost only" tone="active" />
                  <SafetyBoundaryBadge label={facts.productionAuthorized ? "Production authorized" : "Production unauthorized"} tone={facts.productionAuthorized ? "danger" : "attention"} />
                  <SafetyBoundaryBadge label={`Connectors ${facts.connectorMode}`} tone="idle" />
                  <SafetyBoundaryBadge label={`Financial ${facts.financialExecution}`} tone="idle" />
                  <SafetyBoundaryBadge label={`Trading ${facts.tradingExecution}`} tone="idle" />
                </div>
                <p style={{ color: "var(--text-muted)", fontSize: "var(--fs-sm)" }}>These boundaries are enforced by the server, not this UI. Acknowledge to continue.</p>
              </div>
            )}
            {active.id === "workspace" && (
              <div style={{ display: "grid", gap: 8 }}>
                <Field label="Organization" value={facts.org || "Unavailable"} mono />
                <Field label="Workspace" value={facts.workspace || "Unavailable"} mono />
                <Field label="Your role" value={facts.role || "Unknown"} />
                <p style={{ color: "var(--text-muted)", fontSize: "var(--fs-2xs)" }}>Organization/workspace creation is handled by bootstrap; manage from Settings.</p>
              </div>
            )}
            {active.id === "project" && (
              <div style={{ display: "grid", gap: 8 }}>
                <Field label="Projects available" value={String(d.missions.length ? "—" : facts.projectCount)} />
                <p style={{ color: "var(--text-secondary)", fontSize: "var(--fs-sm)" }}>Missions live inside a project. Create one during mission creation if none exist.</p>
                <button className="ws-chip" onClick={() => router.push("/platform/missions/new")}>Go to mission creation →</button>
              </div>
            )}
            {active.id === "agents" && (
              <div style={{ display: "grid", gap: 8 }}>
                <Field label="Agent bindings" value={String(facts.bindingCount)} />
                <p style={{ color: "var(--text-secondary)", fontSize: "var(--fs-sm)" }}>Agent bindings are governed runtime identities — advisory or execution-capable within a ceiling.</p>
                <button className="ws-chip" onClick={() => router.push("/platform/agents")}>View Agent Constellation →</button>
              </div>
            )}
            {active.id === "approvals" && (
              <p style={{ color: "var(--text-secondary)" }}>Consequential actions require a <b>server-owned approval</b>. The browser never grants authority; it prepares a scoped request and the server decides. Acknowledge to continue.</p>
            )}
            {active.id === "execution" && (
              <p style={{ color: "var(--text-secondary)" }}>All tool execution flows through <b>PlatformAgentRuntime → ExecutionGateway</b>, the sole registered-tool authority. The browser never calls tools directly. Acknowledge to continue.</p>
            )}
            {active.id === "notifications" && (
              <p style={{ color: "var(--text-secondary)" }}>Notifications are a derived view of authorized platform events. Preferences are local; browser notification permission is never requested automatically. Configure later in the Notification Center.</p>
            )}
            {active.id === "voice" && (
              <div style={{ display: "grid", gap: 8 }}>
                <p style={{ color: "var(--text-secondary)" }}>Voice is optional. SaathiOS never requests microphone access during onboarding; discover installed local voices and review privacy limits before choosing a test.</p>
                <button className="ws-chip" onClick={() => router.push("/settings/voice")}>Open Voice Settings →</button>
              </div>
            )}
            {active.id === "ready" && (
              <div style={{ display: "grid", gap: 10 }}>
                <p style={{ color: "var(--text-secondary)" }}>You are ready. Recommended next action:</p>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <button className="ws-chip" onClick={() => router.push("/platform/missions/new")}>Create a mission →</button>
                  <button className="ws-chip" onClick={() => router.push("/platform/actions")}>Operator action queue →</button>
                  <button className="ws-chip" onClick={() => router.push("/platform")}>Spatial home →</button>
                </div>
              </div>
            )}

            <div style={{ display: "flex", gap: 8, marginTop: 16, flexWrap: "wrap" }}>
              {!progress.steps.find((s) => s.id === activeId)?.complete && (
                <button onClick={() => markComplete(activeId)} style={primaryBtn}>
                  {active.safety ? "Acknowledge & continue" : "Mark done & continue"}
                </button>
              )}
              {!active.safety && activeId !== "ready" && (
                <button className="ws-chip" onClick={() => { const idx = ONBOARDING_STEPS.findIndex((s) => s.id === activeId); setActiveId(ONBOARDING_STEPS[idx + 1].id); }}>Skip</button>
              )}
              <button className="ws-chip" onClick={restart} style={{ marginLeft: "auto" }}>Restart onboarding</button>
            </div>
          </SectionPanel>
        </div>
      </RequireSession>
    </SpatialWorkspaceShell>
  );
}

const primaryBtn = { background: "color-mix(in srgb, var(--signal-active) 18%, transparent)", border: "1px solid color-mix(in srgb, var(--signal-active) 50%, transparent)", color: "var(--text-primary)", borderRadius: 10, padding: "8px 16px", cursor: "pointer" };
