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
import { mapSeverityToStatus } from "@/lib/attention";

export default function CommandCenterPage() {
  const [ov, setOv] = useState(null);
  const [attention, setAttention] = useState(null);
  const [err, setErr] = useState(null);
  const [attErr, setAttErr] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    Promise.allSettled([controlOverview(), controlAttention()]).then(([a, b]) => {
      if (cancelled) return;
      if (a.status === "fulfilled") setOv(a.value);
      else setErr(String(a.reason));
      if (b.status === "fulfilled") setAttention(b.value);
      else setAttErr(String(b.reason));
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const items = Array.isArray(attention?.items)
    ? attention.items
    : Array.isArray(attention)
      ? attention
      : [];

  return (
    <div className="page shell-page">
      <div className="shell-page-header">
        <Text tone="muted" size="xs" mono>
          Operate · Command Center
        </Text>
        <Heading level={1} size="xl">
          Command Center
        </Heading>
        <Text tone="muted" size="sm" as="p" className="home-intro">
          Plan and request approval. Execution is never implied from navigation alone.
        </Text>
        <div className="home-header-actions">
          <AuthorityBadge authority="advisory" />
          <StatusBadge status="info" label="Observe" />
          <StatusBadge status="pending" label="Plan" />
          <StatusBadge status="pending" label="Request approval" />
          <StatusBadge status="blocked" label="Execute · gated" />
        </div>
      </div>

      {loading && <LoadingState label="Loading command surfaces…" />}

      {!loading && (
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
            </ul>
            <div className="home-section-actions">
              <Link href="/approvals">
                <Button variant="primary" size="sm">
                  Open Approvals
                </Button>
              </Link>
              <Link href="/control">
                <Button variant="secondary" size="sm">
                  Legacy Control (full M16)
                </Button>
              </Link>
              <Link href="/monitoring">
                <Button variant="outline" size="sm">
                  Monitoring
                </Button>
              </Link>
              <Link href="/control/computer">
                <Button variant="outline" size="sm">
                  Computer agent
                </Button>
              </Link>
            </div>
            <Text tone="disabled" size="xs" mono as="p">
              Control workflows split: search/timeline stay on /control · attention also on Home ·
              approvals on /approvals · health on /monitoring. /control is kept for deep links.
            </Text>
          </Card>

          <Card>
            <Heading level={2} size="md">
              Platform overview
            </Heading>
            {err && !ov && (
              <ErrorState title="Overview unavailable" description="Control overview failed." detail={err} />
            )}
            {ov && (
              <pre className="shell-json mono">
                {JSON.stringify(
                  {
                    keys: Object.keys(ov || {}).slice(0, 14),
                    platform_health: ov?.platform_health?.status || ov?.platform_health?.value ? "present" : "n/a",
                  },
                  null,
                  2
                )}
              </pre>
            )}
            {!err && !ov && <EmptyState title="No overview payload" />}
          </Card>

          <Card>
            <Heading level={2} size="md">
              Attention feed
            </Heading>
            {attErr && !items.length && (
              <ErrorState title="Attention unavailable" detail={attErr} />
            )}
            {!attErr && items.length === 0 && (
              <EmptyState title="No attention items" description="Control attention list is empty or missing." />
            )}
            {items.length > 0 && (
              <ul className="home-continue-list">
                {items.slice(0, 12).map((it, i) => (
                  <li key={it.kind + i}>
                    <StatusBadge status={mapSeverityToStatus(it.severity || "medium")} label={it.severity || "item"} />{" "}
                    {it.message || it.title || it.kind}
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
