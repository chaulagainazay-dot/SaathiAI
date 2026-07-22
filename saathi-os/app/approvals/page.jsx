"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Card,
  Heading,
  Text,
  Button,
  LoadingState,
  ErrorState,
  EmptyState,
  StatusBadge,
  AuthorityBadge,
} from "@/components/ui";
import { platformPendingApprovals } from "@/lib/api";

const SOURCES = [
  { id: "connectors", label: "Connector approvals", integrated: true },
  { id: "missions", label: "Mission proposal decisions", integrated: false },
  { id: "deploy", label: "Deploy / release approvals", integrated: false },
  { id: "trading", label: "Trading approvals", integrated: false },
  { id: "finance", label: "Finance approvals", integrated: false },
];

/**
 * Approval Inbox shell.
 * Missing sources are "not yet integrated" — never counted as zero.
 * This page does not call decide/approve; operators use governed backend flows.
 */
export default function ApprovalsPage() {
  const [items, setItems] = useState(null);
  const [sourceStatus, setSourceStatus] = useState("loading");
  const [err, setErr] = useState(null);

  useEffect(() => {
    let cancelled = false;
    platformPendingApprovals()
      .then((data) => {
        if (cancelled) return;
        const list = Array.isArray(data) ? data : data?.items || data?.approvals || data?.pending;
        if (Array.isArray(list)) {
          setItems(list);
          setSourceStatus("connected");
        } else {
          setItems(null);
          setSourceStatus("unavailable");
          setErr("Unexpected payload shape — not treated as zero approvals");
        }
      })
      .catch((e) => {
        if (cancelled) return;
        setItems(null);
        setSourceStatus("unavailable");
        setErr(String(e));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="page shell-page">
      <div className="shell-page-header">
        <Text tone="muted" size="xs" mono>
          Global · Approvals
        </Text>
        <Heading level={1} size="xl">
          Approval Inbox
        </Heading>
        <Text tone="muted" size="sm" style={{ maxWidth: 560, marginTop: 8, display: "block" }}>
          Cross-area pending gates. This UI does not bypass backend authorization.
        </Text>
        <div style={{ marginTop: 12 }}>
          <AuthorityBadge authority="approval-required" />
        </div>
      </div>

      <div className="shell-page-grid">
        <Card>
          <Heading level={2} size="md">
            Source coverage
          </Heading>
          <ul className="shell-gate-list">
            {SOURCES.map((s) => {
              let badge = { status: "neutral", label: "Not yet integrated" };
              if (s.id === "connectors") {
                if (sourceStatus === "loading") badge = { status: "pending", label: "Loading" };
                else if (sourceStatus === "connected") badge = { status: "success", label: "Connected" };
                else badge = { status: "warning", label: "Unavailable" };
              }
              return (
                <li key={s.id}>
                  <StatusBadge status={badge.status} label={badge.label} /> {s.label}
                </li>
              );
            })}
          </ul>
        </Card>

        <Card>
          <Heading level={2} size="md">
            Connector pending
          </Heading>
          {sourceStatus === "loading" && <LoadingState label="Loading connector approvals…" />}
          {sourceStatus === "unavailable" && (
            <ErrorState
              title="Connector approvals unavailable"
              description="Fetch failed or payload unexpected. This is not displayed as 0 pending."
              detail={err}
            />
          )}
          {sourceStatus === "connected" && items?.length === 0 && (
            <EmptyState
              title="No pending connector approvals"
              description="Connected source returned an empty list. Other sources may still be pending integration."
              note="source: connectors · status: connected"
            />
          )}
          {sourceStatus === "connected" && items?.length > 0 && (
            <div className="shell-agent-list">
              {items.map((it, i) => (
                <div key={it.id || it.approval_id || i} className="shell-agent-row">
                  <div>
                    <div style={{ fontWeight: 500 }}>
                      {it.title || it.action || it.tool || it.id || `Approval ${i + 1}`}
                    </div>
                    <Text tone="muted" size="xs" mono>
                      {it.connector_id || it.account_id || it.status || "pending"}
                    </Text>
                  </div>
                  <StatusBadge status="pending" label="Needs review" />
                </div>
              ))}
              <Text tone="disabled" size="xs" style={{ display: "block", marginTop: 12 }}>
                Decide actions remain on governed connector APIs — not invoked from this shell list.
              </Text>
            </div>
          )}
          <div style={{ marginTop: 16 }}>
            <Link href="/command">
              <Button size="sm" variant="outline">
                Command Center
              </Button>
            </Link>
          </div>
        </Card>
      </div>
    </div>
  );
}
