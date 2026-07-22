"use client";
import { useEffect, useRef } from "react";
import Link from "next/link";
import { useShellChrome } from "./ShellChromeContext";
import {
  Surface,
  Heading,
  Text,
  Button,
  AuthorityBadge,
  EmptyState,
  StatusBadge,
} from "@/components/ui";
import { experienceLabel } from "@/lib/preferences";

/**
 * Bounded Ask Saathi panel scaffold.
 * Does not invent history. No autonomous execution controls.
 */
export default function CopilotPanel() {
  const { copilotOpen, closeCopilot, prefs } = useShellChrome();
  const closeRef = useRef(null);

  useEffect(() => {
    if (copilotOpen) {
      closeRef.current?.focus();
    }
  }, [copilotOpen]);

  if (!copilotOpen) return null;

  const body = experienceLabel(prefs.experience, {
    beginner:
      "Ask Saathi is a helper panel. It will not run sensitive actions for you. Use Approvals or Command Center when something needs your OK.",
    expert:
      "Context-aware Copilot scaffold. Suggested actions are previews only — execution requires approval and governed contracts. Full chat remains on /chat, /workspace, /saathi.",
  });

  return (
    <aside
      className="shell-copilot only-desktop"
      role="complementary"
      aria-label="Ask Saathi"
    >
      <Surface variant="raised" className="shell-copilot-inner">
        <div className="shell-copilot-head">
          <div>
            <Heading level={2} size="md">
              Ask Saathi
            </Heading>
            <div style={{ marginTop: 6 }}>
              <AuthorityBadge authority="advisory" />
            </div>
          </div>
          <button
            ref={closeRef}
            type="button"
            className="shell-topbar-chip"
            onClick={closeCopilot}
            aria-label="Close Ask Saathi"
          >
            Close
          </button>
        </div>

        <Text tone="muted" size="sm" style={{ marginTop: 12, display: "block" }}>
          {body}
        </Text>

        <div style={{ marginTop: 16 }}>
          <StatusBadge status="info" label="Panel scaffold" />
        </div>

        <EmptyState
          title="No ambient conversation yet"
          description="This panel does not invent chat history. Open the full workspace for ongoing sessions, or use Command Center to request governed actions."
          note="Backend conversation is not prefetched here by design."
          action={
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "center" }}>
              <Link href="/chat">
                <Button variant="secondary" size="sm">
                  Open chat
                </Button>
              </Link>
              <Link href="/command">
                <Button variant="outline" size="sm">
                  Command Center
                </Button>
              </Link>
              <Link href="/approvals">
                <Button variant="outline" size="sm">
                  Approvals
                </Button>
              </Link>
            </div>
          }
          style={{ padding: "var(--space-5)" }}
        />

        <Text tone="disabled" size="xs" mono style={{ display: "block", marginTop: 8 }}>
          Esc closes · ] toggles · no direct execution from this panel
        </Text>
      </Surface>
    </aside>
  );
}
