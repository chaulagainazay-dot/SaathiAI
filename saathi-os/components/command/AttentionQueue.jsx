"use client";

import Link from "next/link";
import {
  Heading,
  Text,
  StatusBadge,
  AuthorityBadge,
  RiskBadge,
  EmptyState,
} from "@/components/ui";
import { mapSeverityToStatus } from "@/lib/attention";

function AttentionItem({ item }) {
  return (
    <Link
      href={item.actionRoute || item.href || "/command"}
      className="cmd-attention-item"
      data-severity={item.severity}
    >
      <div className="cmd-attention-badges">
        <StatusBadge status={mapSeverityToStatus(item.severity)} label={item.severity || "info"} />
        <StatusBadge status="info" label={String(item.category || "item").replace(/_/g, " ")} />
        {item.authority === "approval-required" ? (
          <AuthorityBadge authority="approval-required" />
        ) : (
          <AuthorityBadge authority="advisory" />
        )}
        {(item.severity === "critical" || item.severity === "high") && (
          <RiskBadge risk={item.severity === "critical" ? "critical" : "high"} />
        )}
      </div>
      <div className="cmd-attention-body">
        <div className="cmd-attention-title">{item.title}</div>
        {item.summary ? (
          <Text tone="muted" size="sm" as="p">
            {item.summary}
          </Text>
        ) : null}
        <Text tone="disabled" size="xs" mono>
          why: {item.category || "attention"}
          {item.authority ? ` · authority: ${item.authority}` : ""}
          {item.source ? ` · source: ${item.source}` : ""}
          {item.evidenceId ? ` · evidence: ${item.evidenceId}` : " · evidence: none listed"}
        </Text>
      </div>
      <Text tone="muted" size="xs" mono className="cmd-attention-cta">
        {item.actionable ? "act →" : "view →"}
      </Text>
    </Link>
  );
}

export default function AttentionQueue({ attention }) {
  const items = attention?.items || [];
  const high = items.filter((i) => i.severity === "critical" || i.severity === "high");
  const rest = items.filter((i) => i.severity !== "critical" && i.severity !== "high");

  return (
    <section className="cmd-panel surface" aria-labelledby="cmd-attention-heading">
      <div className="cmd-panel-head">
        <Heading level={2} size="md" id="cmd-attention-heading">
          Attention
        </Heading>
        {attention?.partial ? <StatusBadge status="pending" label="Partial sources" /> : null}
        <Text tone="muted" size="xs" mono>
          {items.length} item{items.length === 1 ? "" : "s"}
        </Text>
      </div>
      {!items.length ? (
        <EmptyState
          title="Nothing needs attention"
          description="Approvals, failures, and degradation will appear here when sources report them."
        />
      ) : (
        <div className="cmd-attention-list">
          {high.map((it) => (
            <AttentionItem key={it.id} item={it} />
          ))}
          {rest.slice(0, 12).map((it) => (
            <AttentionItem key={it.id} item={it} />
          ))}
        </div>
      )}
    </section>
  );
}
