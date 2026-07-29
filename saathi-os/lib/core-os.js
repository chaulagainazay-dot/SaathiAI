"use client";

import { API_BASE } from "./api.js";
import { getToken } from "./platform-client.js";

function authHeaders(token) {
  return { "Content-Type": "application/json", "X-Platform-Token": token || getToken() || "" };
}

async function parseJson(response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data?.detail;
    const message =
      (typeof detail === "object" && detail?.message) ||
      detail ||
      data?.message ||
      `Core request failed (${response.status})`;
    const error = new Error(String(message));
    error.status = response.status;
    error.code = detail?.code || data?.code || "";
    throw error;
  }
  return data;
}

export const CORE_NOTICE = {
  unification: "Composes certified runtimes — not a second OS architecture",
  yeti: "Yeti is read-only for financial and assessment mutation; ExecutionGateway remains authoritative",
  production: "Production deployment is not authorized for core unification",
};

export const coreActions = {
  async home(token, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/core/home`, {
      headers: authHeaders(token),
      signal,
    });
    return parseJson(r);
  },
  async health(token, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/core/health`, {
      headers: authHeaders(token),
      signal,
    });
    return parseJson(r);
  },
  async search(token, q, signal) {
    const r = await fetch(
      `${API_BASE}/api/v1/platform/core/search?q=${encodeURIComponent(q || "")}`,
      { headers: authHeaders(token), signal }
    );
    return parseJson(r);
  },
  async yeti(token, question, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/core/yeti`, {
      method: "POST",
      headers: authHeaders(token),
      body: JSON.stringify({ question }),
      signal,
    });
    return parseJson(r);
  },
  async memory(token, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/core/memory`, {
      headers: authHeaders(token),
      signal,
    });
    return parseJson(r);
  },
  async notifications(token, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/core/notifications`, {
      headers: authHeaders(token),
      signal,
    });
    return parseJson(r);
  },
  async commands(token, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/core/commands`, {
      headers: authHeaders(token),
      signal,
    });
    return parseJson(r);
  },
  async context(token, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/core/context`, {
      headers: authHeaders(token),
      signal,
    });
    return parseJson(r);
  },
  async automations(token, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/core/automations`, {
      headers: authHeaders(token),
      signal,
    });
    return parseJson(r);
  },
  async createAutomation(token, body, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/core/automations`, {
      method: "POST",
      headers: authHeaders(token),
      body: JSON.stringify(body),
      signal,
    });
    return parseJson(r);
  },
  async dryRunAutomation(token, id, signal) {
    const r = await fetch(
      `${API_BASE}/api/v1/platform/core/automations/${encodeURIComponent(id)}/dry-run`,
      { method: "POST", headers: authHeaders(token), signal }
    );
    return parseJson(r);
  },
  async saveWorkflow(token, body, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/core/workflows`, {
      method: "POST",
      headers: authHeaders(token),
      body: JSON.stringify(body),
      signal,
    });
    return parseJson(r);
  },
  async listWorkflows(token, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/core/workflows`, {
      headers: authHeaders(token),
      signal,
    });
    return parseJson(r);
  },
  async activity(token, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/core/activity`, {
      headers: authHeaders(token),
      signal,
    });
    return parseJson(r);
  },
};
