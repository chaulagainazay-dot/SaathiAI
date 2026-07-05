// Talks to the SaathiAI platform BFF (FastAPI, port 8765).
// IMPORTANT: an explicitly-set empty string means "same origin" (relative URLs,
// production behind Caddy). Only fall back to localhost when the var is truly
// UNSET (local dev, UI on :3000 + API on :8765). Using `||` here was a bug —
// "" is falsy, so production silently called localhost from the browser/phone.
const _RAW = process.env.NEXT_PUBLIC_SAATHI_API;
export const API_BASE = (_RAW === undefined || _RAW === null) ? "http://localhost:8765" : _RAW;

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

// AI Studio Production Queue — counts by lane + recent runs (confidence/cost/time).
export async function fetchStudioQueue() {
  const r = await fetch(`${API_BASE}/api/v1/studio/queue`, { cache: "no-store" });
  if (!r.ok) throw new Error(`studio ${r.status}`);
  return r.json();
}

// AI Lab — Prompt Library catalog (name · active version · scores).
export async function fetchLabPrompts() {
  const r = await fetch(`${API_BASE}/api/v1/lab/prompts`, { cache: "no-store" });
  if (!r.ok) throw new Error(`lab ${r.status}`);
  return r.json();
}

export async function fetchLabPrompt(name) {
  const r = await fetch(`${API_BASE}/api/v1/lab/prompts/${encodeURIComponent(name)}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`lab ${r.status}`);
  return r.json();
}

export async function rollbackLabPrompt(name, version) {
  const r = await fetch(`${API_BASE}/api/v1/lab/prompts/${encodeURIComponent(name)}/rollback`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ version }),
  });
  if (!r.ok) throw new Error(`lab ${r.status}`);
  return r.json();
}

// Talk to Saathi (the conversation brain). Same-origin cookie auth — the user
// must be logged in on the dashboard. Returns { reply } or throws on 401.
export async function sendChat(text, sessionId = "dashboard") {
  const r = await fetch(`${API_BASE}/api/v1/agent/chat`, {
    method: "POST", credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, session_id: sessionId }),
  });
  if (r.status === 401) throw new Error("unauthorized");
  if (!r.ok) throw new Error(`chat ${r.status}`);
  return r.json();
}

// Today's daily IELTS Mission (lesson topic + checklist + streak).
export async function fetchMission() {
  const r = await fetch(`${API_BASE}/api/v1/mission`, { cache: "no-store" });
  if (!r.ok) throw new Error(`mission ${r.status}`);
  return r.json();
}

// Mark a daily IELTS Mission item done (lesson/speaking/writing/quiz).
export async function completeMission(item) {
  const r = await fetch(`${API_BASE}/api/v1/mission/complete`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ item, done: true }),
  });
  if (!r.ok) throw new Error(`mission ${r.status}`);
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
