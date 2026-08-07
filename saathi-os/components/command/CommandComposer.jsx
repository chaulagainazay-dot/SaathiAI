"use client";

import Link from "next/link";
import { Heading, Text, Button, StatusBadge, Input } from "@/components/ui";
import { useShellChrome } from "@/components/shell/ShellChromeContext";

/**
 * Command entry: text + open copilot + voice handoff.
 * Does not own microphone/TTS — docks remain global; V-NEXT-1 will unify.
 */
export default function CommandComposer({ command, voiceSessionState }) {
  const { openCopilot } = useShellChrome();
  const vs = voiceSessionState || command?.voiceSessionState || "UNKNOWN";

  return (
    <section className="cmd-panel surface cmd-composer" aria-labelledby="cmd-composer-heading">
      <div className="cmd-panel-head">
        <Heading level={2} size="md" id="cmd-composer-heading">
          Command
        </Heading>
        <StatusBadge status="info" label={`VOICE ${vs}`} />
        <AuthorityHint />
      </div>
      <Text tone="muted" size="sm" as="p">
        {command?.note ||
          "Plan and request approval. Voice recognition and chat never grant execution authority."}
      </Text>
      <div className="cmd-composer-row">
        <Input
          className="cmd-composer-input"
          readOnly
          aria-label="Command input opens Ask Saathi copilot"
          placeholder={command?.placeholder || "Ask Saathi…"}
          onFocus={() => openCopilot?.()}
          onClick={() => openCopilot?.()}
        />
        <Button variant="primary" size="sm" onClick={() => openCopilot?.()}>
          Ask Saathi
        </Button>
      </div>
      <div className="cmd-composer-actions">
        <Link href="/missions/new">
          <Button size="sm" variant="secondary">
            New mission
          </Button>
        </Link>
        <Link href="/chat">
          <Button size="sm" variant="outline">
            Chat
          </Button>
        </Link>
        <Link href="/settings/voice">
          <Button size="sm" variant="outline">
            Voice settings
          </Button>
        </Link>
        <Link href="/approvals">
          <Button size="sm" variant="outline">
            Approvals
          </Button>
        </Link>
      </div>
      <Text tone="disabled" size="xs" mono as="p">
        Reserved voice states: OFF READY LISTENING THINKING SPEAKING INTERRUPTED DEGRADED ERROR —
        only real data shown ({vs}). Mic/TTS ownership stays with existing providers until V-NEXT-1.
      </Text>
    </section>
  );
}

function AuthorityHint() {
  return <StatusBadge status="pending" label="OBSERVE · PLAN · APPROVE · EXECUTE GATED" />;
}
