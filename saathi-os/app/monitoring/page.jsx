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
          Observability surface. No privileged execution controls here.
        </Text>
        <div className="home-header-actions">
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
          {!loading && !err && !health && (
            <EmptyState title="No health payload" description="Endpoint returned empty." />
          )}
          {!loading && health && <pre className="shell-json mono">{JSON.stringify(health, null, 2).slice(0, 2000)}</pre>}
        </Card>
        <Card>
          <Heading level={2} size="md">
            Related surfaces
          </Heading>
          <div className="home-section-actions home-section-actions-col">
            <Link href="/infrastructure">
              <Button variant="secondary" size="sm">
                Infrastructure
              </Button>
            </Link>
            <Link href="/control">
              <Button variant="outline" size="sm">
                Legacy Control
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
          </div>
        </Card>
      </div>
    </div>
  );
}
