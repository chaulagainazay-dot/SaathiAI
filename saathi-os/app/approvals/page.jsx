"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  Card,
  Heading,
  Text,
  Button,
  Input,
  LoadingState,
  ErrorState,
  EmptyState,
  StatusBadge,
  AuthorityBadge,
  RiskBadge,
  EnvironmentBadge,
  EvidenceBadge,
  ConfirmDialog,
} from "@/components/ui";
import {
  platformPendingApprovals,
  platformDecideApproval,
  controlApprovals,
  fetchRecommendations,
  decideRecommendation,
} from "@/lib/api";
import {
  aggregateApprovals,
  extractList,
  filterApprovals,
  sortApprovals,
} from "@/lib/approvals";

function settled(p) {
  return p.then((value) => ({ ok: true, value })).catch((error) => ({ ok: false, error: String(error) }));
}

/**
 * Multi-source Approval Inbox.
 * Decisions only via existing authorized APIs with explicit ConfirmDialog.
 */
export default function ApprovalsPage() {
  const [loading, setLoading] = useState(true);
  const [bundle, setBundle] = useState(null);
  const [q, setQ] = useState("");
  const [type, setType] = useState("all");
  const [status, setStatus] = useState("all");
  const [sort, setSort] = useState("urgency");
  const [pendingDecision, setPendingDecision] = useState(null);
  const [deciding, setDeciding] = useState(false);
  const [decideError, setDecideError] = useState(null);
  const [decideOk, setDecideOk] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    const [conn, cell, recs] = await Promise.all([
      settled(platformPendingApprovals()),
      settled(controlApprovals()),
      settled(fetchRecommendations({ status: "pending", limit: 40 })),
    ]);
    const connList = conn.ok ? extractList(conn.value) : null;
    const recList = recs.ok ? extractList(recs.value) || recs.value?.recommendations : null;

    const agg = aggregateApprovals({
      connectors: Array.isArray(connList) ? connList : [],
      connectorsStatus: conn.ok && Array.isArray(connList) ? "connected" : "unavailable",
      connectorsError: conn.ok ? (Array.isArray(connList) ? null : "unexpected payload shape") : conn.error,
      controlCell: cell.ok ? cell.value : null,
      controlStatus: cell.ok ? "connected" : "unavailable",
      controlError: cell.ok ? null : cell.error,
      recommendations: Array.isArray(recList) ? recList : [],
      recommendationsStatus: recs.ok && Array.isArray(recList) ? "connected" : "unavailable",
      recommendationsError: recs.ok ? (Array.isArray(recList) ? null : "unexpected payload") : recs.error,
    });
    setBundle(agg);
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const visible = useMemo(() => {
    if (!bundle) return [];
    return sortApprovals(filterApprovals(bundle.items, { status, type, q }), sort);
  }, [bundle, status, type, q, sort]);

  const runDecision = async (accept) => {
    if (!pendingDecision?.decideId || !pendingDecision?.decideKind) return;
    setDeciding(true);
    setDecideError(null);
    setDecideOk(null);
    try {
      if (pendingDecision.decideKind === "connector") {
        await platformDecideApproval(pendingDecision.decideId, accept);
      } else if (pendingDecision.decideKind === "recommendation") {
        await decideRecommendation(pendingDecision.decideId, accept);
      } else {
        throw new Error("No authorized decision contract for this item");
      }
      setDecideOk(accept ? "Approved via authorized API" : "Rejected via authorized API");
      setPendingDecision(null);
      await load();
    } catch (e) {
      setDecideError(String(e));
    } finally {
      setDeciding(false);
    }
  };

  const pendingLabel =
    bundle?.hasConnectedSource && typeof bundle.pendingTotal === "number"
      ? `${bundle.pendingTotal} from connected sources`
      : "Pending total unavailable";

  return (
    <div className="page shell-page">
      <div className="shell-page-header">
        <Text tone="muted" size="xs" mono>
          Global · Approvals
        </Text>
        <Heading level={1} size="xl">
          Approval Inbox
        </Heading>
        <Text tone="muted" size="sm" as="p" className="home-intro">
          Multi-source pending gates. Unavailable sources are not shown as zero. Decisions use existing
          authorized APIs only after explicit confirmation.
        </Text>
        <div className="home-header-actions">
          <AuthorityBadge authority="approval-required" />
          {bundle?.partial && <StatusBadge status="pending" label="Partial aggregation" />}
          <StatusBadge
            status={bundle?.hasConnectedSource ? "info" : "warning"}
            label={pendingLabel}
          />
        </div>
      </div>

      {loading && <LoadingState label="Loading approval sources…" />}

      {!loading && bundle && (
        <div className="shell-page-grid approvals-layout">
          <Card>
            <Heading level={2} size="md">
              Source coverage
            </Heading>
            <ul className="home-source-list">
              {bundle.sources.map((s) => (
                <li key={s.id}>
                  <StatusBadge
                    status={
                      s.status === "connected"
                        ? "success"
                        : s.status === "not_integrated"
                          ? "neutral"
                          : s.status === "partial"
                            ? "pending"
                            : "warning"
                    }
                    label={s.status.replace(/_/g, " ")}
                  />
                  <span>
                    {s.label}
                    {typeof s.count === "number" ? ` · ${s.count}` : ""}
                    {s.error ? ` · ${s.error}` : ""}
                  </span>
                </li>
              ))}
            </ul>
            <Text tone="disabled" size="xs" mono as="p">
              not_integrated ≠ empty · unavailable ≠ 0
            </Text>
          </Card>

          <Card className="approvals-main">
            <div className="approvals-filters">
              <Input
                placeholder="Filter title / source…"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                aria-label="Filter approvals"
              />
              <select
                className="approvals-select"
                value={type}
                onChange={(e) => setType(e.target.value)}
                aria-label="Type"
              >
                <option value="all">All types</option>
                <option value="connector">Connector</option>
                <option value="recommendation">Recommendation</option>
                <option value="control_summary">Control summary</option>
              </select>
              <select
                className="approvals-select"
                value={status}
                onChange={(e) => setStatus(e.target.value)}
                aria-label="Status"
              >
                <option value="all">All statuses</option>
                <option value="pending">Pending</option>
              </select>
              <select
                className="approvals-select"
                value={sort}
                onChange={(e) => setSort(e.target.value)}
                aria-label="Sort"
              >
                <option value="urgency">Urgency</option>
                <option value="age">Age</option>
              </select>
            </div>

            {decideOk && <StatusBadge status="success" label={decideOk} />}
            {decideError && (
              <ErrorState title="Decision failed" description="Server rejected or network error." detail={decideError} />
            )}

            {!bundle.hasConnectedSource && (
              <ErrorState
                title="No approval sources connected"
                description="All integrated sources failed or returned unexpected payloads. This is not displayed as zero pending."
              />
            )}

            {bundle.hasConnectedSource && visible.length === 0 && (
              <EmptyState
                title="No matching pending items"
                description="Connected sources returned no rows for the current filters (or truly empty lists)."
                note="Empty connected list is distinct from unavailable."
              />
            )}

            {visible.length > 0 && (
              <div className="shell-agent-list">
                {visible.map((it) => (
                  <div key={it.id} className="shell-agent-row approvals-row">
                    <div>
                      <div className="home-attention-title">{it.title}</div>
                      <Text tone="muted" size="xs" as="p">
                        {it.summary}
                      </Text>
                      <div className="home-attention-badges">
                        <StatusBadge status="pending" label={it.status} />
                        <StatusBadge status="info" label={it.type} />
                        <AuthorityBadge authority="approval-required" />
                        <RiskBadge
                          risk={
                            ["critical", "high", "elevated", "low", "unknown"].includes(String(it.risk).toLowerCase())
                              ? String(it.risk).toLowerCase() === "elevated"
                                ? "elevated"
                                : String(it.risk).toLowerCase()
                              : "unknown"
                          }
                        />
                        {it.environment && <EnvironmentBadge env={it.environment} />}
                        {it.evidenceRefs?.length > 0 && <EvidenceBadge present />}
                        <Text tone="disabled" size="xs" mono>
                          {it.source}
                          {it.createdAt ? ` · ${it.createdAt}` : ""}
                          {it.expiresAt ? ` · exp ${it.expiresAt}` : ""}
                        </Text>
                      </div>
                    </div>
                    <div className="approvals-row-actions">
                      {it.canDecide ? (
                        <>
                          <Button
                            size="sm"
                            variant="primary"
                            onClick={() => {
                              setDecideError(null);
                              setPendingDecision({ ...it, _accept: true });
                            }}
                          >
                            Approve…
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => {
                              setDecideError(null);
                              setPendingDecision({ ...it, _accept: false });
                            }}
                          >
                            Reject…
                          </Button>
                        </>
                      ) : (
                        <Link href={it.decisionRoute || "/command"}>
                          <Button size="sm" variant="secondary">
                            Open surface
                          </Button>
                        </Link>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}

            <div className="home-section-actions">
              <Link href="/command">
                <Button size="sm" variant="outline">
                  Command Center
                </Button>
              </Link>
              <Button size="sm" variant="ghost" onClick={load}>
                Refresh
              </Button>
            </div>
          </Card>
        </div>
      )}

      <ConfirmDialog
        open={Boolean(pendingDecision)}
        title={pendingDecision?._accept ? "Confirm approval" : "Confirm rejection"}
        description={
          pendingDecision
            ? `This calls the existing authorized ${pendingDecision.decideKind} API for “${pendingDecision.title}”. Server-side authorization still applies. No silent auto-confirm.`
            : ""
        }
        confirmLabel={pendingDecision?._accept ? "Approve" : "Reject"}
        cancelLabel="Cancel"
        loading={deciding}
        destructive={!pendingDecision?._accept}
        onCancel={() => !deciding && setPendingDecision(null)}
        onConfirm={() => runDecision(Boolean(pendingDecision?._accept))}
      />
    </div>
  );
}
