// Talks to the SaathiAI platform BFF (FastAPI, port 8765).
export const API_BASE =
  process.env.NEXT_PUBLIC_SAATHI_API || "http://localhost:8765";

export async function fetchCeoHome() {
  const r = await fetch(`${API_BASE}/api/executive/briefing`, { cache: "no-store" });
  if (!r.ok) throw new Error(`bff ${r.status}`);
  return r.json();
}

// Unified infrastructure diagnostics (Models · Browser · Connectors · Conversation + score).
export async function fetchInfraHealth() {
  const r = await fetch(`${API_BASE}/api/v1/infrastructure/health`, { cache: "no-store" });
  if (!r.ok) throw new Error(`infra ${r.status}`);
  return r.json();
}

// Today's Operating System — one aggregated home-screen call (all real).
export async function fetchCeoOs() {
  const r = await fetch(`${API_BASE}/api/v1/ceo/os`, { cache: "no-store" });
  if (!r.ok) throw new Error(`ceo-os ${r.status}`);
  return r.json();
}

// Platform Maturity — the honest mirror (Infrastructure vs Applications vs Real Data).
export async function fetchMaturity() {
  const r = await fetch(`${API_BASE}/api/v1/platform/maturity`, { cache: "no-store" });
  if (!r.ok) throw new Error(`maturity ${r.status}`);
  return r.json();
}

// Automation Center — status, health score, recent runs (flight recorder).
export async function fetchAutomation() {
  const r = await fetch(`${API_BASE}/api/v1/human/automation`, { cache: "no-store" });
  if (!r.ok) throw new Error(`automation ${r.status}`);
  return r.json();
}

export async function fetchRun(runId) {
  const r = await fetch(`${API_BASE}/api/v1/human/runs/${runId}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`run ${r.status}`);
  return r.json();
}

// Click-to-test the Human Browser Driver end-to-end (token-gated).
export async function testHumanBrowser(token) {
  const r = await fetch(`${API_BASE}/api/v1/human/test`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "x-saathi-token": token || "" },
    body: JSON.stringify({}),
  });
  if (r.status === 401) return { ok: false, error: "unauthorized — wrong SAATHI_TOKEN" };
  return r.json();
}
