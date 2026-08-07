"use client";

import Link from "next/link";
import { Heading, Text, Button, StatusBadge, Input } from "@/components/ui";
import { useShellChrome } from "@/components/shell/ShellChromeContext";
import { useVoiceSession } from "@/components/voice/VoiceSessionProvider";
import { useVoiceRuntime } from "@/components/voice/VoiceRuntimeProvider";

/**
 * Command entry: text + open copilot + canonical voice session.
 * Does NOT own microphone/TTS — invokes VoiceSessionManager / VoiceRuntime only.
 */
export default function CommandComposer({ command, voiceSessionState }) {
  const { openCopilot } = useShellChrome();
  const voiceSession = useVoiceSession();
  // Shell always mounts VoiceRuntimeProvider above routes.
  const runtimeApi = useVoiceRuntime();
  const vs =
    voiceSession?.commandLabel ||
    voiceSessionState ||
    command?.voiceSessionState ||
    "UNKNOWN";
  const caps = voiceSession?.capabilities || {};

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
          "Plan and request approval. Voice never grants execution authority."}
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
        {runtimeApi ? (
          <Button
            size="sm"
            variant="secondary"
            onClick={() => runtimeApi.toggleMic?.()}
            disabled={runtimeApi.busy && !runtimeApi.runtime?.recording}
            aria-label={runtimeApi.micLabel || "Toggle microphone"}
          >
            {runtimeApi.runtime?.recording ? "Stop mic" : "Mic"}
          </Button>
        ) : null}
        {voiceSession?.session?.state === "SPEAKING" || runtimeApi?.runtime?.speaking ? (
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              voiceSession?.interrupt?.("USER_CANCEL");
              runtimeApi?.interrupt?.();
            }}
          >
            Interrupt
          </Button>
        ) : null}
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
        Canonical VoiceSession: {vs}
        {voiceSession?.session?.transcriptPartial
          ? ` · partial “${String(voiceSession.session.transcriptPartial).slice(0, 48)}”`
          : ""}
        {" · "}
        caps: mic={String(!!caps.microphoneAvailable)} stt=
        {String(!!caps.speechRecognitionAvailable)} vad=false wake=false duplex=false
        {" · "}manual interrupt only
      </Text>
    </section>
  );
}

function AuthorityHint() {
  return <StatusBadge status="pending" label="OBSERVE · PLAN · APPROVE · EXECUTE GATED" />;
}
