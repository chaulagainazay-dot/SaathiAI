"use client";

import { useVoiceOutput } from "./VoiceOutputProvider";

function providerLabel(provider) {
  return {
    macos_system: "macOS system voice",
    voxcpm: "VoxCPM",
    unavailable: "Unavailable",
    auto: "Automatic",
  }[provider] || provider || "Checking provider";
}

export default function VoiceOutputDock() {
  const voice = useVoiceOutput();
  if (!voice.token) return null;

  const operation = voice.output.operation;
  const provider =
    operation?.provider ||
    voice.metadata.health?.default_provider ||
    "unavailable";
  const canPlay = voice.output.audioReady && voice.output.state === "completed";
  const canStop = voice.busy || voice.output.state === "playing" || canPlay;

  return (
    <section
      className="voice-output-dock"
      data-voice-state={voice.output.state}
      aria-label="Speech output controls"
    >
      <div className="voice-output-head">
        <strong>Voice output</strong>
        <label className="voice-output-toggle">
          <input
            type="checkbox"
            checked={voice.preferences.enabled}
            onChange={async (event) => {
              const enabled = event.target.checked;
              if (!enabled) await voice.stop();
              voice.updatePreferences({ enabled });
            }}
            aria-label="Enable speech output"
          />
          {voice.preferences.enabled ? "Enabled" : "Disabled"}
        </label>
      </div>

      <div className="voice-output-settings">
        <label>
          <span>Voice</span>
          <select
            aria-label="Voice profile"
            value={voice.preferences.profileId}
            onChange={(event) =>
              voice.updatePreferences({ profileId: event.target.value })
            }
            disabled={!voice.preferences.enabled || voice.metadata.loading}
          >
            {(voice.metadata.profiles.length
              ? voice.metadata.profiles
              : [{ profile_id: "saathi_default", display_name: "SaathiOS Default" }]
            ).map((profile) => (
              <option key={profile.profile_id} value={profile.profile_id}>
                {profile.display_name}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Rate {voice.preferences.speakingRate.toFixed(1)}×</span>
          <input
            aria-label="Speaking rate"
            type="range"
            min="0.5"
            max="2"
            step="0.1"
            value={voice.preferences.speakingRate}
            onChange={(event) =>
              voice.updatePreferences({
                speakingRate: Number(event.target.value),
              })
            }
            disabled={!voice.preferences.enabled}
          />
        </label>
      </div>

      <div className="voice-output-actions">
        {canPlay ? (
          <button
            type="button"
            className="voice-action"
            onClick={voice.play}
            aria-label="Play synthesized speech"
          >
            Play
          </button>
        ) : null}
        {canStop ? (
          <button
            type="button"
            className="voice-action voice-action-stop"
            onClick={() => voice.stop()}
            aria-label="Stop speaking"
          >
            Stop speaking
          </button>
        ) : null}
      </div>

      <p className="voice-output-state" role="status" aria-live="polite">
        {voice.output.message}
      </p>
      <p className="voice-output-provider">
        Provider: {providerLabel(provider)}
        {operation?.fallbackUsed ? " · fallback used" : ""}
      </p>
      {voice.metadata.error ? (
        <button
          type="button"
          className="voice-output-retry"
          onClick={voice.refresh}
        >
          Provider unavailable · Retry
        </button>
      ) : null}
    </section>
  );
}
