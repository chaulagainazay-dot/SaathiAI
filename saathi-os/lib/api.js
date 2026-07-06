// Talks to the SaathiAI platform BFF (FastAPI, port 8765).
// IMPORTANT: an explicitly-set empty string means "same origin" (relative URLs,
// production behind Caddy). Only fall back to localhost when the var is truly
// UNSET (local dev, UI on :3000 + API on :8765). Using `||` here was a bug —
// "" is falsy, so production silently called localhost from the browser/phone.
const _RAW = process.env.NEXT_PUBLIC_SAATHI_API;
export const API_BASE = (_RAW === undefined || _RAW === null) ? "http://localhost:8765" : _RAW;

// LOCAL_BASE = Mac-only capabilities (voice/STT, code-memory) that must run on the
// machine with the mic + binary. On the local build, API_BASE points at the VM (one
// source of truth for DATA) while LOCAL_BASE stays localhost for these. On the VM
// build, both are the same origin.
const _LOCAL = process.env.NEXT_PUBLIC_LOCAL_API;
export const LOCAL_BASE = (_LOCAL === undefined || _LOCAL === null) ? API_BASE : _LOCAL;

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

// Code Memory (codebase-memory-mcp) connector status + indexed projects.
export async function fetchCodeMemory() {
  const r = await fetch(`${LOCAL_BASE}/api/v1/code-memory/status`, { cache: "no-store" });
  if (!r.ok) throw new Error(`code-memory ${r.status}`);
  return r.json();
}

// ── Client Intake — Create New Project ──────────────────────────────────────
export async function fetchProjects() {
  const r = await fetch(`${API_BASE}/api/v1/intake/projects`, { cache: "no-store" });
  if (!r.ok) throw new Error(`projects ${r.status}`); return r.json();
}
export async function createProject(data = {}) {
  const r = await fetch(`${API_BASE}/api/v1/intake/projects`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
  if (!r.ok) throw new Error(`create ${r.status}`); return r.json();
}
export async function fetchProject(id) {
  const r = await fetch(`${API_BASE}/api/v1/intake/projects/${id}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`project ${r.status}`); return r.json();
}
export async function updateProject(id, data, status) {
  const r = await fetch(`${API_BASE}/api/v1/intake/projects/${id}`, {
    method: "PATCH", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ data, status }) });
  if (!r.ok) throw new Error(`update ${r.status}`); return r.json();
}
export async function researchProject(id) {
  const r = await fetch(`${API_BASE}/api/v1/intake/projects/${id}/research`, { method: "POST" });
  if (!r.ok) throw new Error(`research ${r.status}`); return r.json();
}
export async function fetchIntakeForm(token) {
  const r = await fetch(`${API_BASE}/api/v1/intake/form/${token}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`form ${r.status}`); return r.json();
}
export async function submitIntakeForm(token, data) {
  const r = await fetch(`${API_BASE}/api/v1/intake/form/${token}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ data }) });
  if (!r.ok) throw new Error(`submit ${r.status}`); return r.json();
}

// Log in (sets the httponly session cookie so chat/writes are authorized).
export async function login(password) {
  const r = await fetch(`${API_BASE}/api/v1/auth/login`, {
    method: "POST", credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });
  return r.json();   // { ok: true } | { ok: false, error }
}

// Director Library — imported agency Directors (slug/name/description).
export async function fetchDirectors() {
  const r = await fetch(`${API_BASE}/api/v1/directors`, { cache: "no-store" });
  if (!r.ok) throw new Error(`directors ${r.status}`);
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

// Voice turn: send recorded audio → { transcript, reply, reply_audio_b64, reply_audio_mime }.
export async function sendVoice(blob, sessionId = "web") {
  const fd = new FormData();
  fd.append("file", blob, "speech.webm");
  fd.append("session_id", sessionId);
  fd.append("speak_reply", "true");
  fd.append("require_wake", "false");
  const r = await fetch(`${LOCAL_BASE}/api/v1/voice/command`, { method: "POST", body: fd });
  if (!r.ok) throw new Error(`voice ${r.status}`);
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

// SaathiAI Studio — today's production brief (Director/Planner).
export async function fetchStudioPlan() {
  const r = await fetch(`${API_BASE}/api/v1/studio/plan`, { cache: "no-store" });
  if (!r.ok) throw new Error(`plan ${r.status}`);
  return r.json();
}

// Studio Executive — run the full department pipeline (Research→Creative→Script).
export async function fetchStudioProduce() {
  const r = await fetch(`${API_BASE}/api/v1/studio/produce`, { cache: "no-store" });
  if (!r.ok) throw new Error(`produce ${r.status}`);
  return r.json();
}

// AI Studio OS — the whole content factory in one read (Control Room).
export async function fetchControlRoom() {
  const r = await fetch(`${API_BASE}/api/v1/studio/control-room`, { cache: "no-store" });
  if (!r.ok) throw new Error(`control-room ${r.status}`);
  return r.json();
}

// Missions — the CEO OS dashboard of every business (Mission = root object).
export async function fetchMissions(status = "") {
  const q = status ? `?status=${status}` : "";
  const r = await fetch(`${API_BASE}/api/v1/missions${q}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`missions ${r.status}`);
  return r.json();
}

// Missions — one Mission's Executive Dashboard (identity + KPIs + evidence + learning + events).
export async function fetchMissionDetail(id) {
  const r = await fetch(`${API_BASE}/api/v1/missions/${id}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`mission ${r.status}`);
  return r.json();
}

// Missions — ＋New Mission: create a Business Digital Twin (research + departments + briefing + roadmap).
export async function createMissionTwin(payload) {
  const r = await fetch(`${API_BASE}/api/v1/missions/twin`, {
    method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new Error(`create-twin ${r.status}`);
  return r.json();
}

// Mission Intake — apply structured onboarding into the Knowledge Graph (no OAuth).
export async function applyIntake(missionId, payload) {
  const r = await fetch(`${API_BASE}/api/v1/missions/${missionId}/intake`, {
    method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload) });
  if (!r.ok) throw new Error(`intake ${r.status}`);
  return r.json();
}
export async function extractDocument(missionId, title, text) {
  const r = await fetch(`${API_BASE}/api/v1/missions/${missionId}/document`, {
    method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title, text }) });
  if (!r.ok) throw new Error(`document ${r.status}`);
  return r.json();
}

// Proposal Director — generate the full Proposal Package from a Mission twin.
export async function generateProposal(missionId) {
  const r = await fetch(`${API_BASE}/api/v1/missions/${missionId}/proposal`, {
    method: "POST", credentials: "include" });
  if (!r.ok) throw new Error(`proposal ${r.status}`);
  return r.json();
}
export async function fetchProposal(missionId) {
  const r = await fetch(`${API_BASE}/api/v1/missions/${missionId}/proposal`, { cache: "no-store" });
  if (!r.ok) throw new Error(`proposal ${r.status}`);
  return r.json();
}
export async function decideProposal(missionId, accept) {
  const r = await fetch(`${API_BASE}/api/v1/missions/${missionId}/proposal/decide`, {
    method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ accept }) });
  if (!r.ok) throw new Error(`decide ${r.status}`);
  return r.json();
}

// Event Bus — volume by type/source + routing table (the spine every product emits to).
export async function fetchEventStats(days = 30) {
  const r = await fetch(`${API_BASE}/api/v1/events/stats?days=${days}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`event-stats ${r.status}`);
  return r.json();
}

// Event Bus — recent events (filter by type glob / source).
export async function fetchEvents({ type = "", source = "", limit = 30 } = {}) {
  const q = new URLSearchParams({ type, source, limit: String(limit) });
  const r = await fetch(`${API_BASE}/api/v1/events?${q}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`events ${r.status}`);
  return r.json();
}

// Learning — run all 3 Learning Directors over the Evidence Store (recommend-only).
export async function runLearningAnalysis() {
  const r = await fetch(`${API_BASE}/api/v1/learning/analyze`, { cache: "no-store" });
  if (!r.ok) throw new Error(`learning-analyze ${r.status}`);
  return r.json();
}

// Learning — list recommendations (searchable by category/status).
export async function fetchRecommendations({ category = "", status = "", limit = 60 } = {}) {
  const q = new URLSearchParams({ category, status, limit: String(limit) });
  const r = await fetch(`${API_BASE}/api/v1/learning/recommendations?${q}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`recommendations ${r.status}`);
  return r.json();
}

// Learning — CEO accepts/rejects a recommendation (nothing auto-changes).
export async function decideRecommendation(id, accept, implemented_in = "") {
  const r = await fetch(`${API_BASE}/api/v1/learning/decide`, {
    method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id, accept, implemented_in }),
  });
  if (!r.ok) throw new Error(`decide ${r.status}`);
  return r.json();
}

// Evidence Service — CEO roll-up across every department (shared memory).
export async function fetchEvidenceStats(days = 30) {
  const r = await fetch(`${API_BASE}/api/v1/evidence/stats?days=${days}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`evidence-stats ${r.status}`);
  return r.json();
}

// Evidence Service — raw query (filter by department/project/episode).
export async function fetchEvidence({ department = "", episode = "", limit = 50 } = {}) {
  const q = new URLSearchParams({ department, episode, limit: String(limit) });
  const r = await fetch(`${API_BASE}/api/v1/evidence?${q}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`evidence ${r.status}`);
  return r.json();
}

// Script Director — generate today's structured episode document.
export async function fetchStudioScript() {
  const r = await fetch(`${API_BASE}/api/v1/studio/script`, { cache: "no-store" });
  if (!r.ok) throw new Error(`script ${r.status}`);
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
