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
  EnvironmentBadge,
} from "@/components/ui";
import { fetchInfraHealth, API_BASE } from "@/lib/api";
import { inferEnvironment } from "@/lib/navigation";
import InfraHealthWorkspace from "@/components/infra/InfraHealthWorkspace";

/**
 * Canonical Monitoring — observe-only.
 * M47.5: includes full infrastructure health workspace (legacy /infrastructure redirects here).
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
        <Text tone="muted" size="sm" as="p" className="home-intro">
          Observability surface — infrastructure health, raw diagnostics, and related ops links. No
          privileged execution controls here.
        </Text>
        <div className="home-header-actions">
          <EnvironmentBadge env={env} />
          <StatusBadge status="info" label="Observe only" />
          <StatusBadge status="success" label="Includes Infrastructure" />
        </div>
      </div>

      <section className="home-card" aria-label="Infrastructure health">
        <InfraHealthWorkspace />
      </section>

      <div className="shell-page-grid" style={{ marginTop: 20 }}>
        <Card>
          <Heading level={2} size="md">
            Raw health payload
          </Heading>
          {loading && <LoadingState label="Loading infrastructure health…" />}
          {!loading && err && (
            <ErrorState
              title="Health endpoint unavailable"
              description="Honest failure — not shown as healthy. Engine warning light above may still poll separately."
              detail={err}
            />
          )}
          {!loading && !err && !health && (
            <EmptyState title="No health payload" description="Endpoint returned empty." />
          )}
          {!loading && health && (
            <pre className="shell-json mono">{JSON.stringify(health, null, 2).slice(0, 2000)}</pre>
          )}
        </Card>
        <Card>
          <Heading level={2} size="md">
            Related surfaces
          </Heading>
          <div className="home-section-actions home-section-actions-col">
            <Link href="/control">
              <Button variant="outline" size="sm">
                Legacy Control Center
              </Button>
            </Link>
            <Link href="/command">
              <Button variant="outline" size="sm">
                Command Center
              </Button>
            </Link>
            <Link href="/evidence">
              <Button variant="outline" size="sm">
                Evidence
              </Button>
            </Link>
            <Link href="/security">
              <Button variant="secondary" size="sm">
                Security
              </Button>
            </Link>
          </div>
          <Text tone="disabled" size="xs" mono as="p">
            Legacy /infrastructure soft-redirects here (M47.5).
          </Text>
        </Card>
      </div>
    </div>
  );
}
