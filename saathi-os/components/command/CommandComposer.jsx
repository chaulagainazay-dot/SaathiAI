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
      {(voiceSession?.session?.transcriptPartial ||
        voiceSession?.session?.transcriptFinal ||
        voiceSession?.session?.lastTurn) && (
        <div className="cmd-transcript-panel" aria-live="polite">
          {voiceSession?.session?.transcriptPartial ? (
            <Text tone="muted" size="sm" as="p" className="cmd-transcript-partial">
              <strong>Partial (not executable):</strong>{" "}
              {String(voiceSession.session.transcriptPartial).slice(0, 200)}
            </Text>
          ) : null}
          {voiceSession?.session?.transcriptFinal || voiceSession?.session?.lastTurn?.text ? (
            <Text tone="default" size="sm" as="p" className="cmd-transcript-final">
              <strong>Final turn:</strong>{" "}
              {String(
                voiceSession.session.lastTurn?.text || voiceSession.session.transcriptFinal || ""
              ).slice(0, 200)}
              {voiceSession.session.lastTurn?.isExecutable === false
                ? " · non-executable / backchannel"
                : voiceSession.session.lastTurn
                  ? " · ready for review (not auto-run)"
                  : ""}
            </Text>
          ) : null}
          {voiceSession?.session?.sttDegraded ? (
            <Text tone="muted" size="xs" as="p">
              STT degraded: {voiceSession.session.sttDegradedReason || "fallback"}
            </Text>
          ) : null}
        </div>
      )}
      {voiceSession?.session?.voiceInputLabel ? (
        <Text tone="muted" size="xs" as="p" className="cmd-voice-input-label">
          <strong>{voiceSession.session.voiceInputLabel.title || "VOICE INPUT"}</strong>
          {" · "}
          {voiceSession.session.voiceInputLabel.line}
          {voiceSession.session.sttEngine?.language
            ? ` · lang ${voiceSession.session.sttEngine.language}`
            : ""}
          {voiceSession.session.sttEngine?.degraded ? " · degraded" : ""}
        </Text>
      ) : null}
      <Text tone="disabled" size="xs" mono as="p">
        Canonical VoiceSession: {vs}
        {voiceSession?.session?.lastBargeInLatencyMs != null
          ? ` · barge-in ${Math.round(voiceSession.session.lastBargeInLatencyMs)}ms`
          : ""}
        {voiceSession?.session?.interruptClass
          ? ` · interrupt ${voiceSession.session.interruptClass}`
          : ""}
        {" · "}
        caps: stt={String(!!caps.streamingSttAvailable)} partial=
        {String(!!caps.partialTranscriptAvailable)} vad=
        {String(!!caps.vadAvailable)} bargeIn=
        {String(!!caps.acousticBargeInAvailable)} wake=false duplex=false
        {" · "}
        partial≠execute · privacy=
        {voiceSession?.session?.sttEngine?.privacyClass ||
          voiceSession?.session?.voiceInputLabel?.privacyClass ||
          "PLATFORM_MANAGED_UNKNOWN"}
      </Text>
    </section>
  );
}

function AuthorityHint() {
  return <StatusBadge status="pending" label="OBSERVE · PLAN · APPROVE · EXECUTE GATED" />;
}
