"use client";
import Link from "next/link";
import {
  Card,
  Heading,
  Text,
  Button,
  StatusBadge,
  AuthorityBadge,
  RiskBadge,
  EvidenceBadge,
  LoadingState,
  EmptyState,
  ErrorState,
} from "@/components/ui";
import MobileHome from "@/components/mobile/MobileHome";
import { useAttentionHome } from "@/lib/useAttentionHome";
import { mapSeverityToStatus } from "@/lib/attention";
import { useShellChrome } from "@/components/shell/ShellChromeContext";
import { experienceLabel } from "@/lib/preferences";

function MetricTile({ label, metric, href }) {
  if (!metric || metric.status === "unavailable") {
    return (
      <Link href={href || "#"} className="home-metric home-metric-unavail">
        <Text tone="muted" size="xs" mono>
          {label}
        </Text>
        <StatusBadge status="warning" label="Unavailable" />
      </Link>
    );
  }
  return (
    <Link href={href || "#"} className="home-metric">
      <Text tone="muted" size="xs" mono>
        {label}
      </Text>
      <div className="home-metric-value">{metric.value}</div>
    </Link>
  );
}

function AttentionRow({ item }) {
  return (
    <Link href={item.actionRoute || item.href || "/command"} className="home-attention-row">
      <div className="home-attention-badges">
        <StatusBadge status={mapSeverityToStatus(item.severity)} label={item.severity} />
        <StatusBadge status="info" label={item.category.replace(/_/g, " ")} />
        {item.authority === "approval-required" ? (
          <AuthorityBadge authority="approval-required" />
        ) : (
          <AuthorityBadge authority="advisory" />
        )}
        {item.category === "evidence_ready" && <EvidenceBadge present />}
        {(item.severity === "critical" || item.severity === "high") && (
          <RiskBadge risk={item.severity === "critical" ? "critical" : "high"} />
        )}
      </div>
      <div className="home-attention-body">
        <div className="home-attention-title">{item.title}</div>
        {item.summary && (
          <Text tone="muted" size="sm" as="p">
            {item.summary}
          </Text>
        )}
        <Text tone="disabled" size="xs" mono>
          {item.source}
          {item.createdAt ? ` · ${item.createdAt}` : ""}
        </Text>
      </div>
      <Text tone="muted" size="xs" mono>
        open →
      </Text>
    </Link>
  );
}

export default function HomePage() {
  const { loading, attention, projects, projectsStatus, missionsContinue } = useAttentionHome();
  const { openCopilot, prefs } = useShellChrome();

  const summary = attention?.summary;
  const items = attention?.items || [];
  const highPriority = items.filter((i) => i.severity === "critical" || i.severity === "high");
  const rest = items.filter((i) => i.severity !== "critical" && i.severity !== "high");
  const evidenceItems = items.filter((i) => i.category === "evidence_ready");
  const systemItems = items.filter((i) => i.category === "degraded_system" || i.category === "security_attention");

  const intro = experienceLabel(prefs.experience, {
    beginner: "This page shows what needs you now. Nothing sensitive runs from here — Approvals and Command Center handle decisions.",
    expert: "Attention spine aggregates control, missions, approvals, infra, and evidence. Partial source failure is preserved; unavailable metrics are never shown as zero.",
  });

  return (
    <>
      <div className="only-mobile">
        <MobileHome />
      </div>

      <div className="only-desktop page shell-page home-page">
        <header className="shell-page-header home-header">
          <Text tone="muted" size="xs" mono>
            Operate · Home
          </Text>
          <Heading level={1} size="xl">
            What needs attention
          </Heading>
          <Text tone="muted" size="sm" as="p" className="home-intro">
            {intro}
          </Text>
          <div className="home-header-actions">
            <AuthorityBadge authority="advisory" label="Navigation only · no direct execution" />
            {attention?.partial && <StatusBadge status="pending" label="Partial aggregation" />}
            <Button variant="primary" size="sm" onClick={openCopilot}>
              Ask Saathi
            </Button>
          </div>
        </header>

        {loading && <LoadingState label="Loading attention sources…" />}

        {!loading && !attention && (
          <ErrorState
            title="Attention spine unavailable"
            description="No attention sources could be loaded. Open Command Center or Monitoring directly."
            action={
              <Link href="/command">
                <Button size="sm">Command Center</Button>
              </Link>
            }
          />
        )}

        {!loading && attention && (
          <>
            {/* A. Operational summary */}
            <section className="home-metrics" aria-label="Operational summary">
              <MetricTile label="Critical / high" metric={summary?.critical} href="/" />
              <MetricTile label="Pending approvals" metric={summary?.pendingApprovals} href="/approvals" />
              <MetricTile label="Blocked missions" metric={summary?.blockedMissions} href="/missions" />
              <MetricTile label="Failed / attention runs" metric={summary?.failedRuns} href="/command" />
              <MetricTile label="Degraded systems" metric={summary?.degradedSystems} href="/monitoring" />
              <MetricTile label="Recent evidence" metric={summary?.recentEvidence} href="/evidence" />
            </section>

            <div className="home-grid">
              {/* B. Needs attention */}
              <section className="home-col" aria-label="Needs attention">
                <Card className="home-card">
                  <div className="home-section-head">
                    <Heading level={2} size="md">
                      Needs attention
                    </Heading>
                    <StatusBadge
                      status={highPriority.length ? "warning" : "success"}
                      label={highPriority.length ? `${highPriority.length} high` : "Clear"}
                    />
                  </div>
                  {[...highPriority, ...rest].length === 0 ? (
                    <EmptyState
                      title="Nothing needs you right now"
                      description="Connected sources returned no open attention items."
                      note={`sources connected: ${summary?.sourcesConnected ?? 0} · failed: ${summary?.sourcesFailed ?? 0}`}
                    />
                  ) : (
                    <div className="home-attention-list">
                      {[...highPriority, ...rest].slice(0, 24).map((item) => (
                        <AttentionRow key={item.id} item={item} />
                      ))}
                    </div>
                  )}
                </Card>
              </section>

              <div className="home-side">
                {/* C. Continue working */}
                <Card className="home-card">
                  <Heading level={2} size="md">
                    Continue working
                  </Heading>
                  {missionsContinue.length === 0 && projects.length === 0 ? (
                    <EmptyState
                      title="No active workstreams"
                      description={
                        projectsStatus === "unavailable"
                          ? "Projects source unavailable — not shown as empty success."
                          : "No active missions or recent projects from connected APIs."
                      }
                      action={
                        <Link href="/missions">
                          <Button size="sm" variant="secondary">
                            Missions
                          </Button>
                        </Link>
                      }
                    />
                  ) : (
                    <ul className="home-continue-list">
                      {missionsContinue.map((m) => (
                        <li key={m.id}>
                          <Link href={`/missions/${m.id}`}>
                            <StatusBadge status="success" label="mission" /> {m.name || m.key}
                          </Link>
                        </li>
                      ))}
                      {projects.map((p) => (
                        <li key={p.id}>
                          <Link href="/projects">
                            <StatusBadge status="info" label="project" /> {p.name || p.data?.name || p.id}
                          </Link>
                        </li>
                      ))}
                    </ul>
                  )}
                </Card>

                {/* D. Recent evidence */}
                <Card className="home-card">
                  <Heading level={2} size="md">
                    Recent evidence
                  </Heading>
                  {evidenceItems.length === 0 ? (
                    <EmptyState
                      title="No evidence items in attention feed"
                      description="Open the Evidence store for a full browse."
                      action={
                        <Link href="/evidence">
                          <Button size="sm" variant="outline">
                            Evidence
                          </Button>
                        </Link>
                      }
                    />
                  ) : (
                    <ul className="home-continue-list">
                      {evidenceItems.map((e) => (
                        <li key={e.id}>
                          <Link href="/evidence">
                            <EvidenceBadge present /> {e.title}
                          </Link>
                        </li>
                      ))}
                    </ul>
                  )}
                </Card>

                {/* E. System posture */}
                <Card className="home-card">
                  <Heading level={2} size="md">
                    System posture
                  </Heading>
                  <ul className="home-source-list">
                    {(attention.sources || []).map((s) => (
                      <li key={s.id}>
                        <StatusBadge
                          status={
                            s.status === "connected"
                              ? "success"
                              : s.status === "unavailable" || s.status === "error"
                                ? "warning"
                                : "neutral"
                          }
                          label={s.status}
                        />
                        <span>
                          {s.label}
                          {typeof s.count === "number" ? ` · ${s.count}` : ""}
                        </span>
                      </li>
                    ))}
                  </ul>
                  {systemItems.length > 0 && (
                    <div className="home-attention-list home-system-extra">
                      {systemItems.slice(0, 4).map((item) => (
                        <AttentionRow key={item.id} item={item} />
                      ))}
                    </div>
                  )}
                  <div className="home-section-actions">
                    <Link href="/monitoring">
                      <Button size="sm" variant="outline">
                        Monitoring
                      </Button>
                    </Link>
                    <Link href="/command">
                      <Button size="sm" variant="secondary">
                        Command Center
                      </Button>
                    </Link>
                  </div>
                </Card>
              </div>
            </div>
          </>
        )}
      </div>
    </>
  );
}
