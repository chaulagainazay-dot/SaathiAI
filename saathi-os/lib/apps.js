"use client";

import { API_BASE } from "./api.js";
import { getToken } from "./platform-client.js";

function authHeaders(token) {
  return { "Content-Type": "application/json", "X-Platform-Token": token };
}

async function parseJson(response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data?.detail;
    const message =
      (typeof detail === "object" && detail?.message) ||
      detail ||
      data?.message ||
      `App request failed (${response.status})`;
    const error = new Error(String(message));
    error.status = response.status;
    error.code = detail?.code || data?.code || "";
    throw error;
  }
  return data;
}

export const appActions = {
  async health(token, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/apps/health`, {
      headers: authHeaders(token),
      signal,
    });
    return parseJson(r);
  },
  async launcher(token, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/apps/launcher`, {
      headers: authHeaders(token),
      signal,
    });
    return parseJson(r);
  },
  async list(token, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/apps`, {
      headers: authHeaders(token),
      signal,
    });
    return parseJson(r);
  },
  async discover(token, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/apps/discover`, {
      method: "POST",
      headers: authHeaders(token),
      signal,
    });
    return parseJson(r);
  },
  async register(token, packageId, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/apps/register`, {
      method: "POST",
      headers: authHeaders(token),
      body: JSON.stringify({ package_id: packageId }),
      signal,
    });
    return parseJson(r);
  },
  async get(token, appId, signal) {
    const r = await fetch(
      `${API_BASE}/api/v1/platform/apps/${encodeURIComponent(appId)}`,
      { headers: authHeaders(token), signal }
    );
    return parseJson(r);
  },
  async enable(token, appId, signal) {
    const r = await fetch(
      `${API_BASE}/api/v1/platform/apps/${encodeURIComponent(appId)}/enable`,
      { method: "POST", headers: authHeaders(token), signal }
    );
    return parseJson(r);
  },
  async disable(token, appId, signal) {
    const r = await fetch(
      `${API_BASE}/api/v1/platform/apps/${encodeURIComponent(appId)}/disable`,
      { method: "POST", headers: authHeaders(token), signal }
    );
    return parseJson(r);
  },
  async launch(token, appId, signal) {
    const r = await fetch(
      `${API_BASE}/api/v1/platform/apps/${encodeURIComponent(appId)}/launch`,
      { method: "POST", headers: authHeaders(token), signal }
    );
    return parseJson(r);
  },
  async favorite(token, appId, favorite = true, signal) {
    const r = await fetch(
      `${API_BASE}/api/v1/platform/apps/${encodeURIComponent(appId)}/favorite`,
      {
        method: "POST",
        headers: authHeaders(token),
        body: JSON.stringify({ favorite }),
        signal,
      }
    );
    return parseJson(r);
  },
  async backup(token, appId, signal) {
    const r = await fetch(
      `${API_BASE}/api/v1/platform/apps/${encodeURIComponent(appId)}/backup`,
      { method: "POST", headers: authHeaders(token), signal }
    );
    return parseJson(r);
  },
  async restore(token, appId, backupId, signal) {
    const r = await fetch(
      `${API_BASE}/api/v1/platform/apps/${encodeURIComponent(appId)}/restore`,
      {
        method: "POST",
        headers: authHeaders(token),
        body: JSON.stringify({ backup_id: backupId }),
        signal,
      }
    );
    return parseJson(r);
  },
  async workflow(token, appId, body = {}, signal) {
    const r = await fetch(
      `${API_BASE}/api/v1/platform/apps/${encodeURIComponent(appId)}/workflow`,
      {
        method: "POST",
        headers: authHeaders(token),
        body: JSON.stringify(body),
        signal,
      }
    );
    return parseJson(r);
  },
};

export function appStateTone(state) {
  const s = String(state || "").toUpperCase();
  if (s === "ENABLED" || s === "RUNNING" || s === "HEALTHY") return "ok";
  if (s === "INSTALLED" || s === "DISABLED" || s === "PAUSED" || s === "UPGRADING")
    return "warn";
  if (s === "QUARANTINED" || s === "REVOKED" || s === "FAILED") return "bad";
  return "muted";
}

export function safeToken() {
  try {
    return getToken() || "";
  } catch {
    return "";
  }
}
