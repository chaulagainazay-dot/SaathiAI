/**
 * Alert delivery — deciding WHAT to send and WHEN. PURE, no I/O.
 *
 * `rules.js` decides whether an alert has fired. This decides whether a fired
 * alert should reach the user, which is a different question and the one that
 * makes alerts usable rather than infuriating.
 *
 * THE HARD PART IS NOT FIRING, IT IS NOT RE-FIRING. A price oscillating around
 * a threshold fires on every evaluation: forty notifications in an hour, after
 * which the user disables alerts entirely and misses the one that mattered. So
 * delivery is gated by state change, a cooldown and a per-window cap, and every
 * suppression is REPORTED rather than silently dropped.
 *
 * NO CREDENTIALS. Delivery targets the browser's own Notification API, which
 * needs the user's permission and nothing else — no push service, no signing
 * key, no account. A rule that cannot be delivered says so.
 */

export const CHANNEL = Object.freeze({
  IN_APP: "IN_APP",
  BROWSER_NOTIFICATION: "BROWSER_NOTIFICATION",
});

export const DELIVERY = Object.freeze({
  SEND: "SEND",
  /** Fired again while already in the fired state — not news. */
  SUPPRESSED_UNCHANGED: "SUPPRESSED_UNCHANGED",
  SUPPRESSED_COOLDOWN: "SUPPRESSED_COOLDOWN",
  SUPPRESSED_RATE_LIMIT: "SUPPRESSED_RATE_LIMIT",
  SUPPRESSED_MUTED: "SUPPRESSED_MUTED",
  /** The user never granted notification permission. */
  CHANNEL_UNAVAILABLE: "CHANNEL_UNAVAILABLE",
});

export const DEFAULT_COOLDOWN_MS = 15 * 60 * 1000;   // 15 minutes per rule
export const DEFAULT_MAX_PER_HOUR = 12;

const ms = (v) => {
  if (v === null || v === undefined || v === "") return null;
  const n = typeof v === "number" ? v : Date.parse(v);
  return Number.isFinite(n) ? n : null;
};

/**
 * Decide delivery for one evaluated rule.
 *
 * `history` is the caller's record for this rule: `{ lastFiredAt, lastState,
 * sentTimestamps }`. Kept as an argument so this stays pure and a UI can replay
 * the decision without a store.
 */
export function decide(result, history = {}, options = {}) {
  const {
    now = Date.now(),
    cooldownMs = DEFAULT_COOLDOWN_MS,
    maxPerHour = DEFAULT_MAX_PER_HOUR,
    muted = false,
    channelAvailable = true,
    channel = CHANNEL.IN_APP,
  } = options;

  if (!result?.fired) {
    // Not firing is not a suppression — it is simply nothing to say.
    return { deliver: false, reason: null, state: "IDLE" };
  }
  if (muted) return suppress(DELIVERY.SUPPRESSED_MUTED);
  if (channel === CHANNEL.BROWSER_NOTIFICATION && !channelAvailable) {
    // Stated, not swallowed: a user who never granted permission should be
    // told their alerts are not reaching them.
    return suppress(DELIVERY.CHANNEL_UNAVAILABLE);
  }

  // An alert that was already firing has not become true again.
  if (history.lastState === "FIRED") return suppress(DELIVERY.SUPPRESSED_UNCHANGED);

  const last = ms(history.lastFiredAt);
  if (last !== null && now - last < cooldownMs) {
    return suppress(DELIVERY.SUPPRESSED_COOLDOWN, { retryAfterMs: cooldownMs - (now - last) });
  }

  const recent = (history.sentTimestamps || [])
    .map(ms).filter((t) => t !== null && now - t < 3_600_000);
  if (recent.length >= maxPerHour) {
    return suppress(DELIVERY.SUPPRESSED_RATE_LIMIT, { sentLastHour: recent.length });
  }

  return { deliver: true, reason: DELIVERY.SEND, state: "FIRED", channel, at: now };
}

function suppress(reason, extra = {}) {
  // Suppression is a decision with a reason, so a UI can explain silence.
  return { deliver: false, reason, state: "FIRED", ...extra };
}

/** Apply a decision to a rule's history. Returns the NEW history. */
export function advance(history = {}, decision, options = {}) {
  const now = options.now ?? decision?.at ?? Date.now();
  if (!decision) return history;
  if (decision.state === "IDLE") {
    // Falling back below the threshold re-arms the alert; without this a rule
    // fires once and never again.
    return { ...history, lastState: "IDLE" };
  }
  if (!decision.deliver) return { ...history, lastState: "FIRED" };
  const sent = [...(history.sentTimestamps || []), now].filter((t) => now - ms(t) < 3_600_000);
  return { ...history, lastState: "FIRED", lastFiredAt: now, sentTimestamps: sent };
}

/** Human-readable notification content. Deterministic, never model-generated. */
export function composeNotification(rule, result) {
  const symbol = rule?.symbol || result?.symbol || "Alert";
  const value = result?.value ?? result?.observed ?? null;
  const target = rule?.value ?? rule?.threshold ?? null;
  const verb = String(rule?.kind || "").toLowerCase().includes("below") ? "fell below" : "reached";
  return {
    title: `${symbol} ${verb} ${target ?? "its target"}`,
    body: value === null ? "Condition met." : `Now ${value}.`,
    tag: `saathios-alert-${rule?.id || symbol}`,
  };
}

/** Whether the browser can deliver at all. Never assumes permission. */
export function channelAvailability() {
  if (typeof window === "undefined" || typeof window.Notification === "undefined") {
    return { available: false, reason: "NOT_SUPPORTED", permission: null };
  }
  const permission = window.Notification.permission;
  return { available: permission === "granted", reason: permission === "granted" ? null : "NOT_GRANTED", permission };
}
