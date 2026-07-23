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
  StatusBadge,
} from "@/components/ui";
import { experienceLabel } from "@/lib/preferences";
import ChatWorkspace from "@/components/chat/ChatWorkspace";

/**
 * Ask Saathi panel — compact ChatWorkspace on the same safe transport as /chat.
 * Full workspace (team/voice/timeline) remains on /chat. No autonomous execution.
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

  const note = experienceLabel(prefs.experience, {
    beginner:
      "Same chat as the full Chat page, in a smaller panel. Sensitive actions still need Approvals or Command Center.",
    expert:
      "Compact ChatWorkspace · same /api/v1/chat/* transport · team/voice/timeline on /chat · no privileged execution here.",
  });

  return (
    <aside className="shell-copilot only-desktop" role="complementary" aria-label="Ask Saathi">
      <Surface variant="raised" className="shell-copilot-inner">
        <div className="shell-copilot-head">
          <div>
            <Heading level={2} size="md">
              Ask Saathi
            </Heading>
            <div style={{ marginTop: 6, display: "flex", gap: 6, flexWrap: "wrap" }}>
              <AuthorityBadge authority="advisory" />
              <StatusBadge status="info" label="Shared chat transport" />
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

        <Text tone="muted" size="xs" as="p" style={{ marginTop: 8 }}>
          {note}
        </Text>

        <div className="shell-copilot-chat" style={{ flex: 1, minHeight: 0, marginTop: 10, overflow: "hidden" }}>
          <ChatWorkspace compact />
        </div>

        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
          <Link href="/chat">
            <Button variant="secondary" size="sm">
              Full chat
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
        <Text tone="disabled" size="xs" mono as="p">
          Esc closes · ] toggles · Stop cancels stream · no direct privileged execution
        </Text>
      </Surface>
    </aside>
  );
}
