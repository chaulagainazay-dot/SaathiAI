/**
 * Bounded local voice-session telemetry.
 * Never records raw audio. Transcripts optional and off by default.
 */

const MAX_EVENTS = 200;

/** @type {{ events: object[], counts: Record<string, number> }} */
const store = {
  events: [],
  counts: Object.create(null),
};

/**
 * @param {string} type
 * @param {object} [meta]
 */
export function recordVoiceTelemetry(type, meta = {}) {
  const event = {
    type: String(type),
    at: new Date().toISOString(),
    // strip forbidden fields if callers pass them
    sessionId: meta.sessionId || null,
    reason: meta.reason || null,
    claimId: meta.claimId || null,
    durationMs: meta.durationMs ?? null,
    errorCode: meta.errorCode || null,
  };
  store.events.push(event);
  if (store.events.length > MAX_EVENTS) {
    store.events.splice(0, store.events.length - MAX_EVENTS);
  }
  store.counts[type] = (store.counts[type] || 0) + 1;
  return event;
}

export function getVoiceTelemetrySnapshot() {
  return {
    events: store.events.slice(),
    counts: { ...store.counts },
  };
}

export function resetVoiceTelemetry() {
  store.events = [];
  store.counts = Object.create(null);
}
