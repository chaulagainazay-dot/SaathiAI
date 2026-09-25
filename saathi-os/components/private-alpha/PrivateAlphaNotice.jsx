"use client";
/**
 * M340 — private-alpha disclosure and failure-state surfaces.
 *
 * Every string here describes what is actually true of a local, invite-only
 * private alpha. Nothing in this file may imply broker connectivity, live market
 * access, account connection, execution readiness or live trading, and nothing
 * here renders a control that does not exist.
 *
 * BlockedState / EmptyState take only className and style, so each state is
 * wrapped in an element that carries the test id and the ARIA role.
 *
 * Presentational only. No fetch, no mutation, no authority.
 */
import { Panel, Pill, Stack, Text, Heading, Badge, EmptyState, BlockedState } from "@/components/ui";

export const PRIVATE_ALPHA_LABELS = [
  "PRIVATE ALPHA",
  "INVITE ONLY",
  "LOCAL ONLY",
  "NOT PRODUCTION",
  "NO BROKER CONNECTIVITY",
  "NO LIVE TRADING",
  "NO ORDER EXECUTION",
  "NO PUBLIC REGISTRATION",
];

export const PRIVATE_ALPHA_LIMITATIONS = [
  "Runs on a single machine, bound to localhost only. There is no public URL.",
  "Access is by owner-issued invitation. There is no public sign-up.",
  "No broker or exchange is connected, and no trading credential is requested or stored.",
  "No account, balance or position is read. No order is submitted, modified or cancelled.",
  "Missions execute through local deterministic tools and mock providers only.",
  "Mutating actions require a human approval. The assistant can never approve its own work.",
  "Backups are owner-managed and local. There is no cloud backup and no external telemetry.",
  "There is no uptime guarantee and no service-level agreement.",
];

/** Persistent disclosure strip. Safe to render on every authenticated surface. */
export function PrivateAlphaBanner({ compact = false }) {
  return (
    <Panel soft data-testid="private-alpha-banner" role="note"
           aria-label="Private alpha status and limitations">
      <Stack gap={3}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {PRIVATE_ALPHA_LABELS.map((label) => (
            <Pill key={label} color="#F5A623">{label}</Pill>
          ))}
        </div>
        <Text size="sm" tone="muted">
          SaathiOS is in private alpha. It runs entirely on this machine, is reachable
          only over localhost, and is available by invitation only. Private-alpha
          readiness does not authorize public production deployment.
        </Text>
        {!compact && (
          <ul data-testid="private-alpha-limitations" style={{ margin: 0, paddingInlineStart: "1.1rem" }}>
            {PRIVATE_ALPHA_LIMITATIONS.map((line) => (
              <li key={line}><Text size="sm" tone="muted">{line}</Text></li>
            ))}
          </ul>
        )}
      </Stack>
    </Panel>
  );
}

/** Shown to anyone who reaches SaathiOS without an invitation. */
export function InviteRequiredNotice({ action }) {
  return (
    <div data-testid="invite-required" role="status">
      <BlockedState
        title="Invitation required"
        reason="PRIVATE_ALPHA_INVITE_ONLY"
        description={
          "SaathiOS private alpha is invite only. There is no public sign-up. " +
          "Ask the owner of this installation to issue you an invitation, then use " +
          "the invitation link to set your password and sign in."
        }
        action={action}
      />
    </div>
  );
}

/** Sign-in guidance. Never reveals whether an account exists. */
export function SignInGuidance() {
  return (
    <Stack gap={2} data-testid="signin-guidance">
      <Text size="sm" tone="muted">
        Sign in with the email your invitation was sent to. If the credentials do
        not match, sign-in fails without indicating which part was wrong.
      </Text>
      <Text size="sm" tone="muted">
        Sessions expire, and the owner can revoke a session at any time. If you are
        signed out unexpectedly, sign in again.
      </Text>
    </Stack>
  );
}

/** Permission denied — states the boundary rather than blaming the user. */
export function PermissionDeniedState({ what = "this action", role }) {
  return (
    <div data-testid="permission-denied" role="status">
      <BlockedState
        title="You do not have permission"
        reason="PERMISSION_DENIED"
        description={
          `Your role${role ? ` (${role})` : ""} does not permit ${what}. ` +
          "Roles are set by the owner of this workspace. Nothing was changed."
        }
      />
    </div>
  );
}

/** Approval pending — makes the human-in-the-loop wait legible. */
export function ApprovalPendingState({ approvalId, requestedAt }) {
  return (
    <div data-testid="approval-pending" role="status" aria-live="polite">
      <EmptyState
        title="Waiting for human approval"
        description={
          "This mission needs a person to approve it before it can run. " +
          "It will not start on its own, and the assistant cannot approve it."
        }
        note={[approvalId && `approval ${approvalId}`, requestedAt && `requested ${requestedAt}`]
          .filter(Boolean).join(" · ")}
      />
    </div>
  );
}

/** Mission is running — progress must be observable, not implied. */
export function MissionRunningState({ missionId, step, note }) {
  return (
    <div data-testid="mission-running" role="status" aria-live="polite">
      <EmptyState
        title="Mission running"
        description={
          "The mission is executing through local tools. You can cancel it at any " +
          "time; cancellation stops the run and records the outcome."
        }
        note={[missionId && `mission ${missionId}`, step && `step ${step}`, note]
          .filter(Boolean).join(" · ")}
      />
    </div>
  );
}

/** Session expired or revoked. */
export function SessionEndedState({ revoked = false }) {
  return (
    <div data-testid="session-ended" role="status">
      <BlockedState
        title={revoked ? "Session revoked" : "Session expired"}
        reason={revoked ? "SESSION_REVOKED" : "SESSION_EXPIRED"}
        description={
          revoked
            ? "The owner revoked this session. Sign in again to continue. Nothing you had in progress was submitted."
            : "This session expired. Sign in again to continue. Nothing you had in progress was submitted."
        }
      />
    </div>
  );
}

/** Mission failure with recovery guidance and a route to evidence. */
export function MissionFailureState({ missionId, errorCode, evidenceHref, diagnosticsHref }) {
  return (
    <div data-testid="mission-failure" role="status">
      <BlockedState
        title="This mission stopped safely"
        reason={errorCode || "MISSION_FAILED"}
        description={
          "The run stopped before completing. Nothing outside this machine was touched, " +
          "and no order, payment or external call was made. " +
          "Open the diagnostics report to see which step stopped and why, then retry or cancel the mission."
        }
        action={
          <Stack direction="row" gap={3}>
            {diagnosticsHref && (
              <a href={diagnosticsHref} data-testid="mission-failure-diagnostics">Open diagnostics</a>
            )}
            {evidenceHref && (
              <a href={evidenceHref} data-testid="mission-failure-evidence">View evidence and audit</a>
            )}
          </Stack>
        }
      />
      {missionId && <Text size="xs" tone="disabled" mono>mission {missionId}</Text>}
    </div>
  );
}

/** A feature that is deliberately absent in private alpha. */
export function UnsupportedFeatureNotice({ feature, why }) {
  return (
    <Panel soft data-testid="unsupported-feature" role="note">
      <Stack gap={2}>
        <Heading level={3} size="sm">{feature} is not available in private alpha</Heading>
        <Text size="sm" tone="muted">
          {why || "This capability is outside the private-alpha boundary. It is not hidden behind a setting — it does not exist in this build."}
        </Text>
        <Badge color="var(--status-warning)" label="OUT OF SCOPE FOR PRIVATE ALPHA" />
      </Stack>
    </Panel>
  );
}

/** Local platform reachability. Never phrased as external connectivity. */
export function LocalPlatformStatus({ online }) {
  return (
    <span data-testid="local-platform-status-detail">
      <Badge
        color={online ? "var(--status-success)" : "var(--status-warning)"}
        label={online ? "Local platform online" : "Local platform offline"}
      />
    </span>
  );
}
