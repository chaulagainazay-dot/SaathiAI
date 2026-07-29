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
      `Fleet request failed (${response.status})`;
    const error = new Error(String(message));
    error.status = response.status;
    error.code = detail?.code || data?.code || "";
    throw error;
  }
  return data;
}

export const fleetActions = {
  async health(token, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/fleet/health`, {
      headers: authHeaders(token),
      signal,
    });
    return parseJson(r);
  },
  async metrics(token, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/fleet/metrics`, {
      headers: authHeaders(token),
      signal,
    });
    return parseJson(r);
  },
  async listWorkers(token, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/fleet/workers`, {
      headers: authHeaders(token),
      signal,
    });
    return parseJson(r);
  },
  async getWorker(token, workerId, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/fleet/workers/${workerId}`, {
      headers: authHeaders(token),
      signal,
    });
    return parseJson(r);
  },
  async registerWorker(token, body, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/fleet/workers/register`, {
      method: "POST",
      headers: authHeaders(token),
      body: JSON.stringify(body),
      signal,
    });
    return parseJson(r);
  },
  async heartbeat(token, workerId, body = {}, signal) {
    const r = await fetch(
      `${API_BASE}/api/v1/platform/fleet/workers/${workerId}/heartbeat`,
      {
        method: "POST",
        headers: authHeaders(token),
        body: JSON.stringify(body),
        signal,
      }
    );
    return parseJson(r);
  },
  async drain(token, workerId, reason = "operator_drain", signal) {
    const r = await fetch(
      `${API_BASE}/api/v1/platform/fleet/workers/${workerId}/drain`,
      {
        method: "POST",
        headers: authHeaders(token),
        body: JSON.stringify({ reason }),
        signal,
      }
    );
    return parseJson(r);
  },
  async quarantine(token, workerId, reason = "operator_quarantine", signal) {
    const r = await fetch(
      `${API_BASE}/api/v1/platform/fleet/workers/${workerId}/quarantine`,
      {
        method: "POST",
        headers: authHeaders(token),
        body: JSON.stringify({ reason }),
        signal,
      }
    );
    return parseJson(r);
  },
  async revoke(token, workerId, reason = "operator_revoke", signal) {
    const r = await fetch(
      `${API_BASE}/api/v1/platform/fleet/workers/${workerId}/revoke`,
      {
        method: "POST",
        headers: authHeaders(token),
        body: JSON.stringify({ reason }),
        signal,
      }
    );
    return parseJson(r);
  },
  async listLeases(token, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/fleet/leases`, {
      headers: authHeaders(token),
      signal,
    });
    return parseJson(r);
  },
  async schedule(token, workNodeId = "", signal) {
    const q = workNodeId ? `?work_node_id=${encodeURIComponent(workNodeId)}` : "";
    const r = await fetch(`${API_BASE}/api/v1/platform/fleet/schedule${q}`, {
      headers: authHeaders(token),
      signal,
    });
    return parseJson(r);
  },
  async reconciliations(token, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/fleet/reconciliations`, {
      headers: authHeaders(token),
      signal,
    });
    return parseJson(r);
  },
  async recover(token, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/fleet/recover`, {
      method: "POST",
      headers: authHeaders(token),
      signal,
    });
    return parseJson(r);
  },
  async dispatch(token, body, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/fleet/dispatch`, {
      method: "POST",
      headers: authHeaders(token),
      body: JSON.stringify(body),
      signal,
    });
    return parseJson(r);
  },
  async reassign(token, body, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/fleet/reassign`, {
      method: "POST",
      headers: authHeaders(token),
      body: JSON.stringify(body),
      signal,
    });
    return parseJson(r);
  },
  async reconcile(token, body, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/fleet/reconcile`, {
      method: "POST",
      headers: authHeaders(token),
      body: JSON.stringify(body),
      signal,
    });
    return parseJson(r);
  },
  async cancel(token, body, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/fleet/cancel`, {
      method: "POST",
      headers: authHeaders(token),
      body: JSON.stringify(body),
      signal,
    });
    return parseJson(r);
  },
  async command(token, message, workerId = "", signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/fleet/command`, {
      method: "POST",
      headers: authHeaders(token),
      body: JSON.stringify({ message, worker_id: workerId }),
      signal,
    });
    return parseJson(r);
  },
  async certify(token, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/fleet/certify`, {
      method: "POST",
      headers: authHeaders(token),
      signal,
    });
    return parseJson(r);
  },
};

export function trustTone(state) {
  const s = String(state || "").toUpperCase();
  if (s === "TRUSTED_LOCAL") return "ok";
  if (s === "DRAINING" || s === "PENDING_ADMISSION") return "warn";
  if (s === "QUARANTINED" || s === "REVOKED" || s === "UNHEALTHY" || s === "OFFLINE")
    return "bad";
  return "muted";
}

export function healthTone(state) {
  const s = String(state || "").toUpperCase();
  if (s === "HEALTHY") return "ok";
  if (s === "DEGRADED" || s === "DRAINING" || s === "STALE") return "warn";
  if (s === "UNHEALTHY" || s === "OFFLINE" || s === "QUARANTINED") return "bad";
  return "muted";
}

export function safeToken() {
  try {
    return getToken() || "";
  } catch {
    return "";
  }
}
