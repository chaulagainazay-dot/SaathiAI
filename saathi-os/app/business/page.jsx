"use client";
import Link from "next/link";
import {
  Card,
  Heading,
  Text,
  Button,
  StatusBadge,
  EmptyState,
  AuthorityBadge,
} from "@/components/ui";
import MobileFinance from "@/components/mobile/MobileFinance";

/**
 * Business OS entry — read-only compose.
 * Finance remains a compatibility surface until a unified metrics API exists.
 * No transaction, payment, or accounting authority is introduced here.
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
        <Text tone="muted" size="sm" as="p" className="home-intro">
          Venture and finance visibility. No fabricated revenue. No payment or trade execution from this
          surface.
        </Text>
        <div className="home-header-actions">
          <StatusBadge status="pending" label="Partial backend" />
          <AuthorityBadge authority="advisory" label="Read-only compose" />
        </div>
      </div>

      <div className="shell-page-grid">
        <Card>
          <Heading level={2} size="md">
            Finance (compatibility)
          </Heading>
          <Text tone="muted" size="sm" as="p">
            Finance modules exist (portfolio / trade journal / revenue) but are not wired to a unified
            dashboard API. This panel does not invent balances or forecasts.
          </Text>
          <div className="home-section-actions">
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
          <Text tone="muted" size="sm" as="p">
            Intake and venture projects.
          </Text>
          <div className="home-section-actions">
            <Link href="/projects">
              <Button size="sm" variant="secondary">
                Open Projects
              </Button>
            </Link>
          </div>
        </Card>
        <Card>
          <Heading level={2} size="md">
            Mobile finance companion
          </Heading>
          <div className="only-desktop">
            <MobileFinance />
          </div>
          <div className="only-mobile">
            <MobileFinance />
          </div>
        </Card>
        <Card>
          <Heading level={2} size="md">
            Venture scaffolds
          </Heading>
          <EmptyState
            title="Per-venture dashboards not unified"
            description="Department routes remain available as legacy scaffolds when they exist."
            note="No fabricated KPI tiles · /finance kept for compatibility"
          />
        </Card>
      </div>
    </div>
  );
}
