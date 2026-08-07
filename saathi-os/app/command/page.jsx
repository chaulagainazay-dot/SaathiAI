"use client";

import Link from "next/link";
import {
  Heading,
  Text,
  Button,
  StatusBadge,
  AuthorityBadge,
  LoadingState,
  ErrorState,
} from "@/components/ui";
import { useCommandCenter } from "@/lib/useCommandCenter";
import AuthorityStrip from "@/components/command/AuthorityStrip";
import CommandComposer from "@/components/command/CommandComposer";
import AttentionQueue from "@/components/command/AttentionQueue";
import ActivityPanel from "@/components/command/ActivityPanel";
import InvestmentSnapshot from "@/components/command/InvestmentSnapshot";
import SystemHealthPanel from "@/components/command/SystemHealthPanel";
import EvidenceTimeline from "@/components/command/EvidenceTimeline";
import { useVoiceSession } from "@/components/voice/VoiceSessionProvider";

/**
 * UI-NEXT-1 + V-NEXT-1 — Central Command with canonical voice session state.
 * Composes existing APIs. No new backend authority. Voice does not execute tools.
 */
export default function CommandCenterPage() {
  const { loading, model, refresh } = useCommandCenter();
  const voiceSession = useVoiceSession();
  const voiceLabel = voiceSession?.commandLabel || model?.command?.voiceSessionState || "UNKNOWN";

  return (
    <div className="page shell-page cmd-page">
      <header className="shell-page-header cmd-header">
        <Text tone="muted" size="xs" mono>
          Operate · Command
        </Text>
        <div className="cmd-header-row">
          <Heading level={1} size="xl">
            SaathiOS Command
          </Heading>
          <div className="cmd-header-actions">
            <AuthorityBadge authority="advisory" label="Compose · no direct execution" />
            <StatusBadge status="blocked" label="LIVE TRADING OFF" />
            <Button size="sm" variant="outline" onClick={() => refresh?.()}>
              Refresh
            </Button>
          </div>
        </div>
        <Text tone="muted" size="sm" as="p" className="home-intro">
          What Saathi is doing, what needs you, what is blocked, and what evidence exists — in one
          place. Plan and request approval; ExecutionGateway remains the only external-action path.
        </Text>
      </header>

      {loading && !model && <LoadingState label="Loading command surfaces…" />}

      {!loading && !model && (
        <ErrorState
          title="Command composition unavailable"
          description="No sources could be composed. Try Monitoring or Home."
          action={
            <Link href="/">
              <Button size="sm">Home</Button>
            </Link>
          }
        />
      )}

      {model && (
        <>
          <AuthorityStrip authority={model.authority} />

          <div className="cmd-mobile-priority only-mobile">
            <CommandComposer command={model.command} voiceSessionState={voiceLabel} />
            <AttentionQueue attention={model.attention} />
            <ActivityPanel activity={model.activity} />
            <SystemHealthPanel systemHealth={model.systemHealth} />
          </div>

          <div className="cmd-layout only-desktop">
            <CommandComposer command={model.command} voiceSessionState={voiceLabel} />

            <div className="cmd-mid-grid">
              <ActivityPanel activity={model.activity} />
              <AttentionQueue attention={model.attention} />
            </div>

            <div className="cmd-mid-grid">
              <InvestmentSnapshot investment={model.investment} />
              <SystemHealthPanel systemHealth={model.systemHealth} />
            </div>

            <EvidenceTimeline timeline={model.timeline} />
          </div>

          <div className="only-mobile">
            <InvestmentSnapshot investment={model.investment} />
            <EvidenceTimeline timeline={model.timeline} />
          </div>

          {model.overviewError ? (
            <Text tone="muted" size="xs" mono as="p">
              Overview source: {model.overviewError}
            </Text>
          ) : null}

          <footer className="cmd-footer">
            <Text tone="disabled" size="xs" mono>
              UI-NEXT-1 composition · inventsMetrics=
              {String(model.meta?.inventsMetrics)} · liveTrading=
              {String(model.meta?.liveTrading)} ·{" "}
              <Link href="/docs" className="cmd-footer-link">
                deep links
              </Link>{" "}
              stay on Missions, Approvals, Trading, Monitoring, Evidence
            </Text>
            <nav className="cmd-footer-nav" aria-label="Command deep links">
              <Link href="/missions">Missions</Link>
              <Link href="/agents">Agents</Link>
              <Link href="/approvals">Approvals</Link>
              <Link href="/trading">Trading</Link>
              <Link href="/monitoring">Monitoring</Link>
              <Link href="/evidence">Evidence</Link>
              <Link href="/settings/voice">Voice</Link>
            </nav>
          </footer>
        </>
      )}
    </div>
  );
}
