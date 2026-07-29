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
      `Orchestration request failed (${response.status})`;
    const error = new Error(String(message));
    error.status = response.status;
    error.code = detail?.code || data?.code || "";
    throw error;
  }
  return data;
}

export const orchestrationActions = {
  async health(token, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/orchestration/health`, {
      headers: authHeaders(token),
      signal,
    });
    return parseJson(r);
  },
  async templates(token, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/orchestration/templates`, {
      headers: authHeaders(token),
      signal,
    });
    return parseJson(r);
  },
  async roles(token, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/orchestration/roles`, {
      headers: authHeaders(token),
      signal,
    });
    return parseJson(r);
  },
  async intake(token, body, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/orchestration/intake`, {
      method: "POST",
      headers: authHeaders(token),
      body: JSON.stringify(body),
      signal,
    });
    return parseJson(r);
  },
  async compile(token, body, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/orchestration/compile`, {
      method: "POST",
      headers: authHeaders(token),
      body: JSON.stringify(body),
      signal,
    });
    return parseJson(r);
  },
  async create(token, body, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/orchestration`, {
      method: "POST",
      headers: authHeaders(token),
      body: JSON.stringify(body),
      signal,
    });
    return parseJson(r);
  },
  async list(token, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/orchestration`, {
      headers: authHeaders(token),
      signal,
    });
    return parseJson(r);
  },
  async get(token, id, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/orchestration/${id}`, {
      headers: authHeaders(token),
      signal,
    });
    return parseJson(r);
  },
  async start(token, id, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/orchestration/${id}/start`, {
      method: "POST",
      headers: authHeaders(token),
      signal,
    });
    return parseJson(r);
  },
  async pause(token, id, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/orchestration/${id}/pause`, {
      method: "POST",
      headers: authHeaders(token),
      signal,
    });
    return parseJson(r);
  },
  async cancel(token, id, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/orchestration/${id}/cancel`, {
      method: "POST",
      headers: authHeaders(token),
      signal,
    });
    return parseJson(r);
  },
  async replan(token, id, body = {}, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/orchestration/${id}/replan`, {
      method: "POST",
      headers: authHeaders(token),
      body: JSON.stringify(body),
      signal,
    });
    return parseJson(r);
  },
  async checkpoint(token, id, signal) {
    const r = await fetch(
      `${API_BASE}/api/v1/platform/orchestration/${id}/checkpoint`,
      { method: "POST", headers: authHeaders(token), signal }
    );
    return parseJson(r);
  },
  async certify(token, id, body = {}, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/orchestration/${id}/certify`, {
      method: "POST",
      headers: authHeaders(token),
      body: JSON.stringify(body),
      signal,
    });
    return parseJson(r);
  },
};

export function stateTone(state) {
  const s = String(state || "").toUpperCase();
  if (s.includes("CERTIFIED")) return "ok";
  if (s === "COMPLETED" || s === "READY" || s === "RUNNING") return "ok";
  if (s.includes("WAITING") || s === "PAUSED" || s === "RETRYING") return "warn";
  if (s === "BLOCKED" || s === "FAILED" || s === "CANCELLED") return "bad";
  return "muted";
}

export function taskStatusLabel(status) {
  return String(status || "UNKNOWN");
}

export function safeToken() {
  try {
    return getToken() || "";
  } catch {
    return "";
  }
}
