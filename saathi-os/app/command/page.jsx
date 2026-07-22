"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Card,
  Heading,
  Text,
  Button,
  StatusBadge,
  AuthorityBadge,
  LoadingState,
  ErrorState,
  EmptyState,
} from "@/components/ui";
import { controlOverview, controlAttention } from "@/lib/api";

/**
 * Command Center — observe / plan / request approval gates.
 * Does not execute privileged actions from this page chrome.
 */
export default function CommandCenterPage() {
  const [ov, setOv] = useState(null);
  const [attention, setAttention] = useState(null);
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.allSettled([controlOverview(), controlAttention()])
      .then(([a, b]) => {
        if (cancelled) return;
        if (a.status === "fulfilled") setOv(a.value);
        else setErr(String(a.reason));
        if (b.status === "fulfilled") setAttention(b.value);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="page shell-page">
      <div className="shell-page-header">
        <Text tone="muted" size="xs" mono className="eyebrow">
          Operate · Command Center
        </Text>
        <Heading level={1} size="xl">
          Command Center
        </Heading>
        <Text tone="muted" size="sm" style={{ maxWidth: 560, marginTop: 8, display: "block" }}>
          Plan and request approval. Execution is never implied from navigation alone.
        </Text>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12 }}>
          <AuthorityBadge authority="advisory" />
          <StatusBadge status="info" label="Observe" />
          <StatusBadge status="pending" label="Plan" />
          <StatusBadge status="pending" label="Request approval" />
          <StatusBadge status="blocked" label="Execute · gated" />
        </div>
      </div>

      <div className="shell-page-grid">
        <Card>
          <Heading level={2} size="md">
            Gates
          </Heading>
          <ul className="shell-gate-list">
            <li>
              <StatusBadge status="info" label="Observe" /> Read-only platform state
            </li>
            <li>
              <StatusBadge status="pending" label="Plan" /> Draft intent — not execution
            </li>
            <li>
              <StatusBadge status="pending" label="Request approval" /> Opens Approval Inbox
            </li>
            <li>
              <StatusBadge status="blocked" label="Execute" /> Only after backend approval
            </li>
            <li>
              <StatusBadge status="blocked" label="Blocked" /> Policy or missing authority
            </li>
          </ul>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 16 }}>
            <Link href="/approvals">
              <Button variant="primary" size="sm">
                Open Approvals
              </Button>
            </Link>
            <Link href="/control">
              <Button variant="secondary" size="sm">
                Legacy Control Center
              </Button>
            </Link>
            <Link href="/monitoring">
              <Button variant="outline" size="sm">
                Monitoring
              </Button>
            </Link>
          </div>
        </Card>

        <Card>
          <Heading level={2} size="md">
            Platform overview
          </Heading>
          {loading && <LoadingState label="Loading control overview…" />}
          {!loading && err && !ov && (
            <ErrorState
              title="Control overview unavailable"
              description="The Command Center could not load live aggregation. Legacy Control remains available."
              detail={err}
              action={
                <Link href="/control">
                  <Button size="sm">Open /control</Button>
                </Link>
              }
            />
          )}
          {!loading && ov && (
            <pre className="shell-json mono">
              {JSON.stringify(
                {
                  platform_health: ov?.platform_health?.value ?? ov?.platform_health ?? "present",
                  security: ov?.security?.value ? "present" : ov?.security ? "present" : "n/a",
                  keys: Object.keys(ov || {}).slice(0, 12),
                },
                null,
                2
              )}
            </pre>
          )}
          {!loading && !ov && !err && (
            <EmptyState title="No overview payload" description="Backend returned an empty overview." />
          )}
        </Card>

        <Card>
          <Heading level={2} size="md">
            Attention
          </Heading>
          {loading && <LoadingState label="Loading attention…" />}
          {!loading && attention && (
            <pre className="shell-json mono">{JSON.stringify(attention, null, 2).slice(0, 1200)}</pre>
          )}
          {!loading && !attention && (
            <EmptyState
              title="Attention feed unavailable"
              description="No attention aggregation in this response. This is not shown as zero items."
              note="source: /api/v1/control/attention"
            />
          )}
        </Card>
      </div>
    </div>
  );
}
