"use client";
import { useEffect, useState } from "react";
import {
  Card,
  Heading,
  Text,
  AuthorityBadge,
  LoadingState,
  ErrorState,
  EmptyState,
  StatusBadge,
} from "@/components/ui";
import { fetchDirectors } from "@/lib/api";

export default function AgentsPage() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetchDirectors()
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e) => {
        if (!cancelled) setErr(String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const list = Array.isArray(data)
    ? data
    : data?.directors || data?.items || data?.agents || null;

  return (
    <div className="page shell-page">
      <div className="shell-page-header">
        <Text tone="muted" size="xs" mono>
          Operate · Agents
        </Text>
        <Heading level={1} size="xl">
          Agents
        </Heading>
        <Text tone="muted" size="sm" style={{ maxWidth: 560, marginTop: 8, display: "block" }}>
          Workforce registry. Authority defaults to advisory. No fabricated running agents.
        </Text>
        <div style={{ marginTop: 12 }}>
          <AuthorityBadge authority="advisory" label="Default authority · advisory" />
        </div>
      </div>

      <Card>
        {loading && <LoadingState label="Loading directors registry…" />}
        {!loading && err && (
          <ErrorState
            title="Agent registry unavailable"
            description="Could not load /api/v1/directors. UI does not invent agent instances."
            detail={err}
          />
        )}
        {!loading && !err && Array.isArray(list) && list.length === 0 && (
          <EmptyState
            title="No agents returned"
            description="The directors endpoint responded with an empty list."
            note="Agent registry UI pending richer aggregation (reliability, cost, workload)."
          />
        )}
        {!loading && !err && Array.isArray(list) && list.length > 0 && (
          <div className="shell-agent-list">
            {list.map((a, i) => {
              const name = a.name || a.id || a.director || `agent-${i}`;
              const auth = a.authority || a.mode || "advisory";
              return (
                <div key={name + i} className="shell-agent-row">
                  <div>
                    <div style={{ fontWeight: 500 }}>{name}</div>
                    <Text tone="muted" size="xs" mono>
                      {a.role || a.kind || a.type || "director"}
                    </Text>
                  </div>
                  <AuthorityBadge
                    authority={
                      ["advisory", "approval-required", "limited-autonomous", "denied", "inactive", "not-exercised"].includes(
                        String(auth).toLowerCase()
                      )
                        ? String(auth).toLowerCase()
                        : "advisory"
                    }
                  />
                </div>
              );
            })}
          </div>
        )}
        {!loading && !err && !Array.isArray(list) && (
          <EmptyState
            title="Agent registry UI pending backend aggregation"
            description="Directors payload is present but not a list shape this view understands. Raw keys are shown for operators; no fake agents."
            note={data ? `keys: ${Object.keys(data).slice(0, 8).join(", ")}` : "no payload"}
          />
        )}
        <div style={{ marginTop: 16 }}>
          <StatusBadge status="info" label="No execute controls on this page" />
        </div>
      </Card>
    </div>
  );
}
