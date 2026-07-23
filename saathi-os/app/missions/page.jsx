"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Card,
  Heading,
  Text,
  Button,
  LoadingState,
  EmptyState,
  ErrorState,
  StatusBadge,
} from "@/components/ui";
import { fetchMissions } from "@/lib/api";

const TYPE_LABEL = {
  business: "Business",
  client: "Client",
  product: "Product",
  startup: "Startup",
  internal: "Internal",
  education: "Education",
  personal: "Personal",
};

function statusBadge(status) {
  const s = String(status || "").toLowerCase();
  if (s === "active") return { status: "success", label: s };
  if (s === "blocked" || s === "failed" || s === "error") return { status: "danger", label: s };
  if (s === "paused" || s === "pending") return { status: "pending", label: s };
  return { status: "neutral", label: s || "unknown" };
}

export default function MissionsPage() {
  const router = useRouter();
  const [missions, setMissions] = useState(null);
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchMissions()
      .then((d) => setMissions(d.missions || []))
      .catch((e) => setErr(String(e)))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="page shell-page">
      <div className="shell-page-header home-header">
        <Text tone="muted" size="xs" mono>
          Operate · Missions
        </Text>
        <div className="home-header-actions" style={{ justifyContent: "space-between", width: "100%" }}>
          <Heading level={1} size="xl">
            Missions
          </Heading>
          <Button variant="primary" size="sm" onClick={() => router.push("/missions/new")}>
            New Mission
          </Button>
        </div>
        <Text tone="muted" size="sm" as="p" className="home-intro">
          Bounded work with lifecycle. Open a mission for intake, proposal, and evidence.
        </Text>
      </div>

      {loading && <LoadingState label="Loading missions…" />}
      {!loading && err && (
        <ErrorState title="Missions unavailable" description="Could not load mission list." detail={err} />
      )}
      {!loading && !err && Array.isArray(missions) && missions.length === 0 && (
        <EmptyState
          title="No missions yet"
          description="Create a mission to start a bounded workstream."
          action={
            <Button size="sm" variant="primary" onClick={() => router.push("/missions/new")}>
              New Mission
            </Button>
          }
        />
      )}

      {!loading && !err && missions?.length > 0 && (
        <div className="missions-grid">
          {missions.map((m) => {
            const st = statusBadge(m.status);
            return (
              <Card
                key={m.id}
                interactive
                className="missions-card"
                onClick={() => router.push(`/missions/${m.id}`)}
              >
                <div className="missions-card-head">
                  <Heading level={2} size="md">
                    {m.name}
                  </Heading>
                  <StatusBadge status="info" label={TYPE_LABEL[m.type] || m.type || "mission"} />
                </div>
                <Text tone="muted" size="xs" mono>
                  {m.key} · {m.department || "—"}
                </Text>
                <div className="home-attention-badges">
                  <StatusBadge status={st.status} label={st.label} />
                </div>
                {m.objectives?.length > 0 && (
                  <ul className="missions-objectives">
                    {m.objectives.slice(0, 3).map((o, i) => (
                      <li key={i}>
                        <Text tone="secondary" size="sm">
                          {o}
                        </Text>
                      </li>
                    ))}
                  </ul>
                )}
                <Text tone="disabled" size="xs">
                  {(m.directors || []).length} directors · open dashboard →
                </Text>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
