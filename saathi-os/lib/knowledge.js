"use client";

import { API_BASE } from "./api.js";
import { getToken } from "./platform-client.js";

function authHeaders(token, extra = {}) {
  return {
    "Content-Type": "application/json",
    "X-Platform-Token": token,
    ...extra,
  };
}

async function parseJson(response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data?.detail;
    const message =
      (typeof detail === "object" && detail?.message) ||
      detail ||
      data?.message ||
      `Knowledge request failed (${response.status})`;
    const error = new Error(String(message));
    error.status = response.status;
    error.code = detail?.code || data?.code || "";
    throw error;
  }
  return data;
}

export const knowledgeActions = {
  async health(token, signal) {
    const response = await fetch(`${API_BASE}/api/v1/platform/knowledge/health`, {
      headers: authHeaders(token),
      signal,
    });
    return parseJson(response);
  },
  async search(token, query, topK = 6, signal) {
    const response = await fetch(`${API_BASE}/api/v1/platform/knowledge/search`, {
      method: "POST",
      headers: authHeaders(token),
      body: JSON.stringify({ query, top_k: topK }),
      signal,
    });
    return parseJson(response);
  },
  async reindex(token, force = false, signal) {
    const response = await fetch(`${API_BASE}/api/v1/platform/knowledge/reindex`, {
      method: "POST",
      headers: authHeaders(token),
      body: JSON.stringify({ force }),
      signal,
    });
    return parseJson(response);
  },
  async completeGrounded(token, message, sessionId = "knowledge-ui", yetiMode = "saathios_help", signal) {
    const response = await fetch(`${API_BASE}/api/v1/platform/conversation/complete`, {
      method: "POST",
      headers: authHeaders(token),
      body: JSON.stringify({
        message,
        session_id: sessionId,
        yeti_mode: yetiMode,
        stream: false,
      }),
      signal,
    });
    return parseJson(response);
  },
};

export function freshnessLabel(freshness) {
  const f = String(freshness || "unknown").toLowerCase();
  if (f === "fresh") return { label: "Fresh", tone: "ok" };
  if (f === "stale") return { label: "Stale", tone: "warn" };
  if (f === "expired") return { label: "Expired", tone: "bad" };
  if (f === "conflicting") return { label: "Conflict", tone: "warn" };
  return { label: "Unknown", tone: "muted" };
}

export function claimKindLabel(kind) {
  const k = String(kind || "").toLowerCase();
  const map = {
    grounded_fact: "Grounded fact",
    inference: "Inference",
    recommendation: "Recommendation",
    unresolved_conflict: "Unresolved conflict",
    unavailable_evidence: "No evidence",
  };
  return map[k] || "Answer";
}

export function safeToken() {
  try {
    return getToken() || "";
  } catch {
    return "";
  }
}
