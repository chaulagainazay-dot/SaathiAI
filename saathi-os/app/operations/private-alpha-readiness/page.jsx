"use client";
/**
 * M343 — Private Alpha Launch Readiness Control Center.
 *
 * READ ONLY. Nothing on this page launches, deploys, publishes, invites a
 * tester, connects a provider, executes an order, or records owner review.
 * Owner review is a human act performed outside this tooling.
 */
import { useState } from "react";
import { Card, Heading, Text, Button, Pill, Badge } from "@/components/ui";
import { PrivateAlphaBanner } from "@/components/private-alpha/PrivateAlphaNotice";
import { useAuthMe } from "@/lib/trading";
import { plat } from "@/lib/platform-client";

const STATE_COLOR = {
  PASS: "#3FB950",
  PASS_WITH_LIMITATION: "#F5A623",
  FAIL: "#FF5A5A",
  NOT_APPLICABLE: "#8FA0C4",
  OWNER_REVIEW_REQUIRED: "#5B8CFF",
};

function Section({ id, title, children }) {
  return (
    <Card data-testid={`readiness-${id}`} style={{ marginBottom: 12 }}>
      <Heading level={2} size="md">{title}</Heading>
      {children}
    </Card>
  );
}

function KeyValue({ label, value, testId }) {
  return (
    <Text className="mono" tone="muted" data-testid={testId}>
      {label}: {value === undefined || value === null ? "—" : String(value)}
    </Text>
  );
}

export default function PrivateAlphaReadinessPage() {
  const auth = useAuthMe();
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);

  const load = async () => {
    if (!auth.token) return;
    setError(null);
    try {
      setReport(await plat("/private-alpha/readiness", { token: auth.token }));
    } catch (cause) {
      setError(cause?.message || String(cause));
    }
  };

  const counts = report?.checklist_counts || {};
  const byCategory = (report?.checklist || []).reduce((acc, entry) => {
    (acc[entry.category] = acc[entry.category] || []).push(entry);
    return acc;
  }, {});

  return (
    <div className="page shell-page" data-testid="private-alpha-readiness-page">
      <header style={{ marginBottom: 16 }}>
        <Heading level={1} size="lg" data-testid="readiness-title">
          Private Alpha Launch Readiness
        </Heading>
        <Text tone="muted" data-testid="readiness-subtitle">
          Read-only. No control on this page launches, deploys, publishes or
          approves anything.
        </Text>
      </header>

      <PrivateAlphaBanner />

      {/* Human review markers — always visible, never satisfied by this page. */}
      <Card data-testid="readiness-human-review" style={{ margin: "12px 0" }}>
        <Heading level={2} size="md">Human review</Heading>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
          <Pill color="#5B8CFF" data-testid="owner-review-required">OWNER_REVIEW_REQUIRED</Pill>
          <Pill color="#F5A623" data-testid="release-not-automatic">PRIVATE_ALPHA_RELEASE_NOT_AUTOMATIC</Pill>
          <Pill color="#FF5A5A" data-testid="public-production-not-authorized">PUBLIC_PRODUCTION_NOT_AUTHORIZED</Pill>
        </div>
        <Text className="mono" tone="muted" style={{ marginTop: 8 }}>
          Automation may not mark owner approval as passed. The owner records the
          decision outside this tooling.
        </Text>
      </Card>

      {error && (
        <Card data-testid="readiness-error" style={{ marginBottom: 12 }}>
          <Text className="mono">{error}</Text>
        </Card>
      )}

      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <Button data-testid="readiness-load" onClick={load}>Load readiness report</Button>
      </div>

      {!auth.token && (
        <Card data-testid="readiness-signin-required">
          <Text tone="muted">Sign in to load the readiness report. This page reads; it never writes.</Text>
        </Card>
      )}

      {report && (
        <>
          <Section id="overview" title="Readiness overview">
            <KeyValue label="verdict" value={report.verdict} testId="readiness-verdict" />
            <KeyValue label="maximum state" value={report.max_state} testId="readiness-max-state" />
            <KeyValue label="branch" value={report.readiness_overview?.branch} testId="readiness-branch" />
            <KeyValue label="release" value={report.readiness_overview?.release_version} />
            <KeyValue label="release gate" value={report.readiness_overview?.release_gate} testId="readiness-release-gate" />
            <KeyValue label="tests" value={report.readiness_overview?.test_results} testId="readiness-tests" />
            <KeyValue label="owner review" value={report.owner_review_status} testId="readiness-owner-review" />
          </Section>

          <Section id="regression-debt" title="Regression debt">
            <KeyValue label="M57 inherited failures" value={report.regression_debt?.m57} testId="readiness-m57" />
            <KeyValue label="M157 inherited failures" value={report.regression_debt?.m157} testId="readiness-m157" />
            <KeyValue label="release-gate failures" value={report.regression_debt?.release_gate} testId="readiness-gate-failures" />
            {(report.regression_debt?.root_causes || []).map((cause, i) => (
              <Text key={i} size="sm" tone="muted" style={{ display: "block", marginTop: 6 }}>{cause}</Text>
            ))}
          </Section>

          <Section id="journey" title="User journey">
            <KeyValue label="verdict" value={report.user_journey?.verdict} testId="readiness-journey-verdict" />
            <KeyValue label="positive steps" value={report.user_journey?.positive_steps} />
            <KeyValue label="refusals proven" value={report.user_journey?.negative_steps} />
            {Object.entries(report.user_journey?.stages || {}).map(([stage, data]) => (
              <Text key={stage} className="mono" tone="muted" style={{ display: "block" }}
                    data-testid={`readiness-stage-${stage}`}>
                {stage}: {data.status} ({data.passed}/{data.steps})
              </Text>
            ))}
          </Section>

          <Section id="reliability" title="Reliability">
            <KeyValue label="soak verdict" value={report.reliability?.soak_verdict} testId="readiness-soak-verdict" />
            <KeyValue label="soak minutes" value={report.reliability?.soak_minutes} testId="readiness-soak-minutes" />
            <KeyValue label="operations" value={report.reliability?.operations} />
            <KeyValue label="error rate" value={report.reliability?.error_rate} testId="readiness-error-rate" />
            <KeyValue label="p95 latency (ms)" value={report.reliability?.latency_ms?.p95} />
            <KeyValue label="memory growth (MB)" value={report.reliability?.resources?.rss_mb_growth} />
            <KeyValue label="concurrency" value={String(report.reliability?.concurrency_ok)} testId="readiness-concurrency" />
            <KeyValue label="recovery" value={String(report.reliability?.recovery_ok)} testId="readiness-recovery" />
          </Section>

          <Section id="security" title="Security">
            <KeyValue label="all authority locks false" value={String(report.security?.all_locks_false)} testId="readiness-locks-false" />
            <KeyValue label="workspace isolation" value={report.security?.workspace_isolation} testId="readiness-isolation" />
            <KeyValue label="session revocation" value={report.security?.session_revocation} />
            <KeyValue label="approval restrictions" value={report.security?.approval_restrictions} />
            <KeyValue label="public registration" value={String(report.security?.public_registration_enabled)} testId="readiness-public-registration" />
            <KeyValue label="broker connectivity" value={report.security?.broker_connectivity} testId="readiness-broker" />
            <KeyValue label="order execution" value={report.security?.order_execution} testId="readiness-order-execution" />
            <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 8 }}
                 data-testid="readiness-authority-locks">
              {Object.entries(report.security?.authority_locks || {}).map(([lock, value]) => (
                <Pill key={lock} color={value ? "#FF5A5A" : "#3FB950"}>
                  {lock}={String(value)}
                </Pill>
              ))}
            </div>
          </Section>

          <Section id="release-package" title="Release package">
            {Object.entries(report.release_package || {}).map(([key, value]) => (
              <Text key={key} className="mono" tone="muted" style={{ display: "block" }}
                    data-testid={`readiness-package-${key}`}>
                {key}: {value || "—"}
              </Text>
            ))}
          </Section>

          <Section id="checklist" title="Launch checklist">
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 10 }}
                 data-testid="readiness-checklist-counts">
              {Object.entries(counts).map(([state, n]) => (
                <Badge key={state} color={STATE_COLOR[state] || "#8FA0C4"} label={`${state} ${n}`} />
              ))}
            </div>
            <div style={{ overflowX: "auto" }}>
              <table data-testid="readiness-checklist" style={{ width: "100%", borderCollapse: "collapse" }}>
                <caption style={{ textAlign: "left", paddingBottom: 6 }}>
                  <Text size="sm" tone="muted">
                    Every item is derived from evidence on disk or a live read. An
                    item whose evidence is missing reports FAIL rather than
                    disappearing.
                  </Text>
                </caption>
                <thead>
                  <tr>
                    <th scope="col" style={{ textAlign: "left" }}>Category</th>
                    <th scope="col" style={{ textAlign: "left" }}>Item</th>
                    <th scope="col" style={{ textAlign: "left" }}>State</th>
                    <th scope="col" style={{ textAlign: "left" }}>Detail</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(byCategory).map(([category, entries]) =>
                    entries.map((entry, i) => (
                      <tr key={`${category}-${i}`}>
                        <th scope="row" style={{ textAlign: "left", fontWeight: 400 }}>
                          <Text className="mono" size="sm" tone="muted">{category}</Text>
                        </th>
                        <td><Text size="sm">{entry.item}</Text></td>
                        <td>
                          <Badge color={STATE_COLOR[entry.state] || "#8FA0C4"} label={entry.state} />
                        </td>
                        <td><Text size="sm" tone="muted">{entry.detail || "—"}</Text></td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </Section>

          <Section id="limitations" title="Known limitations">
            <ul data-testid="readiness-limitations" style={{ margin: 0, paddingInlineStart: "1.1rem" }}>
              {(report.known_limitations || []).map((line) => (
                <li key={line}><Text size="sm" tone="muted">{line}</Text></li>
              ))}
            </ul>
          </Section>
        </>
      )}
    </div>
  );
}
