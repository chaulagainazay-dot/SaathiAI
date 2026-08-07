"use client";

import { API_BASE } from "./api.js";
import { getToken } from "./platform-client.js";

function authHeaders(token) {
  return {
    "Content-Type": "application/json",
    "X-Platform-Token": token,
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
      `Skill request failed (${response.status})`;
    const error = new Error(String(message));
    error.status = response.status;
    error.code = detail?.code || data?.code || "";
    throw error;
  }
  return data;
}

export const skillRuntimeActions = {
  async health(token, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/skills/health`, {
      headers: authHeaders(token),
      signal,
    });
    return parseJson(r);
  },
  async list(token, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/skills`, {
      headers: authHeaders(token),
      signal,
    });
    return parseJson(r);
  },
  async discover(token, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/skills/discover`, {
      method: "POST",
      headers: authHeaders(token),
      signal,
    });
    return parseJson(r);
  },
  async validate(token, packageId, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/skills/validate`, {
      method: "POST",
      headers: authHeaders(token),
      body: JSON.stringify({ package_id: packageId }),
      signal,
    });
    return parseJson(r);
  },
  async register(token, packageId, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/skills/register`, {
      method: "POST",
      headers: authHeaders(token),
      body: JSON.stringify({ package_id: packageId }),
      signal,
    });
    return parseJson(r);
  },
  async get(token, skillId, signal) {
    const r = await fetch(
      `${API_BASE}/api/v1/platform/skills/${encodeURIComponent(skillId)}`,
      { headers: authHeaders(token), signal }
    );
    return parseJson(r);
  },
  async enable(token, skillId, body = {}, signal) {
    const r = await fetch(
      `${API_BASE}/api/v1/platform/skills/${encodeURIComponent(skillId)}/enable`,
      {
        method: "POST",
        headers: authHeaders(token),
        body: JSON.stringify(body),
        signal,
      }
    );
    return parseJson(r);
  },
  async disable(token, skillId, signal) {
    const r = await fetch(
      `${API_BASE}/api/v1/platform/skills/${encodeURIComponent(skillId)}/disable`,
      { method: "POST", headers: authHeaders(token), signal }
    );
    return parseJson(r);
  },
  async execute(token, skillId, body = {}, signal) {
    const r = await fetch(
      `${API_BASE}/api/v1/platform/skills/${encodeURIComponent(skillId)}/execute`,
      {
        method: "POST",
        headers: authHeaders(token),
        body: JSON.stringify(body),
        signal,
      }
    );
    return parseJson(r);
  },
  async upgrade(token, skillId, body, signal) {
    const r = await fetch(
      `${API_BASE}/api/v1/platform/skills/${encodeURIComponent(skillId)}/upgrade`,
      {
        method: "POST",
        headers: authHeaders(token),
        body: JSON.stringify(body),
        signal,
      }
    );
    return parseJson(r);
  },
  async rollback(token, skillId, signal) {
    const r = await fetch(
      `${API_BASE}/api/v1/platform/skills/${encodeURIComponent(skillId)}/rollback`,
      { method: "POST", headers: authHeaders(token), signal }
    );
    return parseJson(r);
  },
  async quarantine(token, skillId, reason = "operator", signal) {
    const r = await fetch(
      `${API_BASE}/api/v1/platform/skills/${encodeURIComponent(skillId)}/quarantine`,
      {
        method: "POST",
        headers: authHeaders(token),
        body: JSON.stringify({ reason }),
        signal,
      }
    );
    return parseJson(r);
  },
  async executions(token, skillId, signal) {
    const r = await fetch(
      `${API_BASE}/api/v1/platform/skills/${encodeURIComponent(skillId)}/executions`,
      { headers: authHeaders(token), signal }
    );
    return parseJson(r);
  },
};

export function skillStateTone(state) {
  const s = String(state || "").toUpperCase();
  if (s === "ENABLED" || s === "VALID" || s === "HEALTHY") return "ok";
  if (s === "DISABLED" || s === "REGISTERED" || s === "DEGRADED" || s === "UPGRADING")
    return "warn";
  if (
    s === "QUARANTINED" ||
    s === "REVOKED" ||
    s === "INVALID" ||
    s === "FAILED" ||
    s.includes("BLOCKED")
  )
    return "bad";
  return "muted";
}

export function safeToken() {
  try {
    return getToken() || "";
  } catch {
    return "";
  }
}
