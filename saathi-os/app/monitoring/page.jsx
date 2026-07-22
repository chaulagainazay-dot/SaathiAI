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
  StatusBadge,
  EnvironmentBadge,
} from "@/components/ui";
import { fetchInfraHealth, API_BASE } from "@/lib/api";
import { inferEnvironment } from "@/lib/navigation";

/**
 * Monitoring — observation only. Command actions live under /command.
 */
export default function MonitoringPage() {
  const [health, setHealth] = useState(null);
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(true);
  const env = inferEnvironment(API_BASE);

  useEffect(() => {
    let cancelled = false;
    fetchInfraHealth()
      .then((d) => {
        if (!cancelled) setHealth(d);
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

  return (
    <div className="page shell-page">
      <div className="shell-page-header">
        <Text tone="muted" size="xs" mono>
          System · Monitoring
        </Text>
        <Heading level={1} size="xl">
          Monitoring
        </Heading>
        <Text tone="muted" size="sm" style={{ maxWidth: 560, marginTop: 8, display: "block" }}>
          Observability surface. No privileged execution controls here.
        </Text>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12 }}>
          <EnvironmentBadge env={env} />
          <StatusBadge status="info" label="Observe only" />
        </div>
      </div>

      <div className="shell-page-grid">
        <Card>
          <Heading level={2} size="md">
            Infrastructure health
          </Heading>
          {loading && <LoadingState label="Loading infrastructure health…" />}
          {!loading && err && (
            <ErrorState
              title="Health endpoint unavailable"
              description="Honest failure — not shown as healthy."
              detail={err}
              action={
                <Link href="/infrastructure">
                  <Button size="sm">Open legacy Infrastructure</Button>
                </Link>
              }
            />
          )}
          {!loading && health && (
            <pre className="shell-json mono">{JSON.stringify(health, null, 2).slice(0, 2000)}</pre>
          )}
        </Card>
        <Card>
          <Heading level={2} size="md">
            Related surfaces
          </Heading>
          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 12 }}>
            <Link href="/infrastructure">
              <Button variant="secondary" size="sm">
                Infrastructure
              </Button>
            </Link>
            <Link href="/control">
              <Button variant="outline" size="sm">
                Legacy Control (read aggregation)
              </Button>
            </Link>
            <Link href="/command">
              <Button variant="outline" size="sm">
                Command Center (actions)
              </Button>
            </Link>
            <Link href="/evidence">
              <Button variant="outline" size="sm">
                Evidence
              </Button>
            </Link>
          </div>
        </Card>
      </div>
    </div>
  );
}
