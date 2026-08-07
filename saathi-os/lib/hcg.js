"use client";

import { API_BASE } from "./api.js";
import { getToken } from "./platform-client.js";

export const HCG_NOTICE = {
  data: "Demo/certification data — not live HCG production",
  qr: "QR means manually verified reference only — no live payment gateway",
  money: "Amounts stored as integer paisa (NPR minor units)",
  production: "Production deployment is not authorized for this mission",
};

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
      `HCG request failed (${response.status})`;
    const error = new Error(String(message));
    error.status = response.status;
    error.code = detail?.code || data?.code || "";
    throw error;
  }
  return data;
}

function tok(token) {
  return token || getToken() || "";
}

export function formatPaisa(minor, currency = "NPR") {
  const n = Number(minor) || 0;
  const sign = n < 0 ? "-" : "";
  const abs = Math.abs(n);
  const major = Math.floor(abs / 100);
  const frac = abs % 100;
  return `${sign}${major}.${String(frac).padStart(2, "0")} ${currency}`;
}

export function safeToken() {
  return getToken() || "";
}

export const hcgActions = {
  async dashboard(token, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/apps/hcg/dashboard`, {
      headers: authHeaders(tok(token)),
      signal,
    });
    return parseJson(r);
  },
  async health(token, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/apps/hcg/health`, {
      headers: authHeaders(tok(token)),
      signal,
    });
    return parseJson(r);
  },
  async seed(token, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/apps/hcg/seed`, {
      method: "POST",
      headers: authHeaders(tok(token)),
      signal,
    });
    return parseJson(r);
  },
  async menu(token, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/apps/hcg/menu`, {
      headers: authHeaders(tok(token)),
      signal,
    });
    return parseJson(r);
  },
  async orders(token, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/apps/hcg/orders`, {
      headers: authHeaders(tok(token)),
      signal,
    });
    return parseJson(r);
  },
  async createOrder(token, body, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/apps/hcg/orders`, {
      method: "POST",
      headers: authHeaders(tok(token)),
      body: JSON.stringify(body),
      signal,
    });
    return parseJson(r);
  },
  async submitKitchen(token, orderId, signal) {
    const r = await fetch(
      `${API_BASE}/api/v1/platform/apps/hcg/orders/${encodeURIComponent(orderId)}/kitchen`,
      { method: "POST", headers: authHeaders(tok(token)), signal }
    );
    return parseJson(r);
  },
  async payment(token, body, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/apps/hcg/payments`, {
      method: "POST",
      headers: authHeaders(tok(token)),
      body: JSON.stringify(body),
      signal,
    });
    return parseJson(r);
  },
  async kitchen(token, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/apps/hcg/kitchen`, {
      headers: authHeaders(tok(token)),
      signal,
    });
    return parseJson(r);
  },
  async kitchenTransition(token, ticketId, toState, signal) {
    const r = await fetch(
      `${API_BASE}/api/v1/platform/apps/hcg/kitchen/${encodeURIComponent(ticketId)}/transition`,
      {
        method: "POST",
        headers: authHeaders(tok(token)),
        body: JSON.stringify({ to_state: toState }),
        signal,
      }
    );
    return parseJson(r);
  },
  async openShift(token, body, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/apps/hcg/shifts/open`, {
      method: "POST",
      headers: authHeaders(tok(token)),
      body: JSON.stringify(body),
      signal,
    });
    return parseJson(r);
  },
  async closeShift(token, shiftId, body, signal) {
    const r = await fetch(
      `${API_BASE}/api/v1/platform/apps/hcg/shifts/${encodeURIComponent(shiftId)}/close`,
      {
        method: "POST",
        headers: authHeaders(tok(token)),
        body: JSON.stringify(body),
        signal,
      }
    );
    return parseJson(r);
  },
  async shifts(token, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/apps/hcg/shifts`, {
      headers: authHeaders(tok(token)),
      signal,
    });
    return parseJson(r);
  },
  async inventory(token, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/apps/hcg/inventory`, {
      headers: authHeaders(tok(token)),
      signal,
    });
    return parseJson(r);
  },
  async stockAdjust(token, body, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/apps/hcg/inventory/adjust`, {
      method: "POST",
      headers: authHeaders(tok(token)),
      body: JSON.stringify(body),
      signal,
    });
    return parseJson(r);
  },
  async customers(token, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/apps/hcg/customers`, {
      headers: authHeaders(tok(token)),
      signal,
    });
    return parseJson(r);
  },
  async customerStatement(token, customerId, signal) {
    const r = await fetch(
      `${API_BASE}/api/v1/platform/apps/hcg/customers/${encodeURIComponent(customerId)}/statement`,
      { headers: authHeaders(tok(token)), signal }
    );
    return parseJson(r);
  },
  async repay(token, body, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/apps/hcg/credit/repay`, {
      method: "POST",
      headers: authHeaders(tok(token)),
      body: JSON.stringify(body),
      signal,
    });
    return parseJson(r);
  },
  async suppliers(token, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/apps/hcg/suppliers`, {
      headers: authHeaders(tok(token)),
      signal,
    });
    return parseJson(r);
  },
  async supplierStatement(token, supplierId, signal) {
    const r = await fetch(
      `${API_BASE}/api/v1/platform/apps/hcg/suppliers/${encodeURIComponent(supplierId)}/statement`,
      { headers: authHeaders(tok(token)), signal }
    );
    return parseJson(r);
  },
  async purchase(token, body, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/apps/hcg/purchases`, {
      method: "POST",
      headers: authHeaders(tok(token)),
      body: JSON.stringify(body),
      signal,
    });
    return parseJson(r);
  },
  async expense(token, body, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/apps/hcg/expenses`, {
      method: "POST",
      headers: authHeaders(tok(token)),
      body: JSON.stringify(body),
      signal,
    });
    return parseJson(r);
  },
  async expenses(token, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/apps/hcg/expenses`, {
      headers: authHeaders(tok(token)),
      signal,
    });
    return parseJson(r);
  },
  async reports(token, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/apps/hcg/reports`, {
      headers: authHeaders(tok(token)),
      signal,
    });
    return parseJson(r);
  },
  async search(token, q, signal) {
    const r = await fetch(
      `${API_BASE}/api/v1/platform/apps/hcg/search?q=${encodeURIComponent(q || "")}`,
      { headers: authHeaders(tok(token)), signal }
    );
    return parseJson(r);
  },
  async notifications(token, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/apps/hcg/notifications`, {
      headers: authHeaders(tok(token)),
      signal,
    });
    return parseJson(r);
  },
  async yeti(token, question, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/apps/hcg/yeti`, {
      method: "POST",
      headers: authHeaders(tok(token)),
      body: JSON.stringify({ question }),
      signal,
    });
    return parseJson(r);
  },
  async backup(token, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/apps/hcg/backup`, {
      method: "POST",
      headers: authHeaders(tok(token)),
      signal,
    });
    return parseJson(r);
  },
  async restore(token, body, signal) {
    const r = await fetch(`${API_BASE}/api/v1/platform/apps/hcg/restore`, {
      method: "POST",
      headers: authHeaders(tok(token)),
      body: JSON.stringify(body),
      signal,
    });
    return parseJson(r);
  },
};
