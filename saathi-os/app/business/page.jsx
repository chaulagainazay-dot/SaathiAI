"use client";
import Link from "next/link";
import {
  Card,
  Heading,
  Text,
  Button,
  StatusBadge,
  EmptyState,
} from "@/components/ui";

/**
 * Business OS entry — composes links to real surfaces.
 * Does not claim a unified business backend.
 */
export default function BusinessPage() {
  return (
    <div className="page shell-page">
      <div className="shell-page-header">
        <Text tone="muted" size="xs" mono>
          Run the business · Business
        </Text>
        <Heading level={1} size="xl">
          Business
        </Heading>
        <Text tone="muted" size="sm" style={{ maxWidth: 560, marginTop: 8, display: "block" }}>
          Venture and finance entry points. Unified Business OS metrics are partial —
          each surface below is only as real as its own API.
        </Text>
        <div style={{ marginTop: 12 }}>
          <StatusBadge status="pending" label="Partial backend" />
        </div>
      </div>

      <div className="shell-page-grid">
        <Card>
          <Heading level={2} size="md">
            Finance
          </Heading>
          <Text tone="muted" size="sm" style={{ display: "block", marginTop: 8 }}>
            Existing finance surface. Not reimplemented here.
          </Text>
          <div style={{ marginTop: 12 }}>
            <Link href="/finance">
              <Button size="sm" variant="secondary">
                Open Finance
              </Button>
            </Link>
          </div>
        </Card>
        <Card>
          <Heading level={2} size="md">
            Projects
          </Heading>
          <Text tone="muted" size="sm" style={{ display: "block", marginTop: 8 }}>
            Intake and venture projects.
          </Text>
          <div style={{ marginTop: 12 }}>
            <Link href="/projects">
              <Button size="sm" variant="secondary">
                Open Projects
              </Button>
            </Link>
          </div>
        </Card>
        <Card>
          <Heading level={2} size="md">
            Venture scaffolds
          </Heading>
          <EmptyState
            title="Per-venture dashboards not unified"
            description="Department routes (cafeteria, travel, etc.) remain available as legacy scaffolds. Business OS will compose real metrics when endpoints exist."
            note="No fabricated revenue or KPI tiles."
          />
        </Card>
      </div>
    </div>
  );
}
