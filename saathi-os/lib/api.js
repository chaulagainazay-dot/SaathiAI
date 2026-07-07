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

// ── cookie-independent session: token in localStorage + x-baadar-session header.
// Works on every browser/device incl. Safari ITP + cross-origin, where cookies fail.
const _tok = () => { try { return localStorage.getItem("saathi_session") || ""; } catch { return ""; } };
export function setSessionToken(t) { try { if (t) localStorage.setItem("saathi_session", t); } catch {} }
export function clearSessionToken() { try { localStorage.removeItem("saathi_session"); } catch {} }
export function afetch(url, opts = {}) {
  const h = { ...(opts.headers || {}) };
  const t = _tok(); if (t) h["x-baadar-session"] = t;
  return fetch(url, { credentials: "include", ...opts, headers: h });
}


export async function fetchCeoHome() {
  const r = await afetch(`${API_BASE}/api/executive/briefing`, { cache: "no-store" });
  if (!r.ok) throw new Error(`bff ${r.status}`);
  return r.json();
}

// Unified infrastructure diagnostics (Models · Browser · Connectors · Conversation + score).
export async function fetchInfraHealth() {
  const r = await afetch(`${API_BASE}/api/v1/infrastructure/health`, { cache: "no-store" });
  if (!r.ok) throw new Error(`infra ${r.status}`);
  return r.json();
}

// AI Studio Production Queue — counts by lane + recent runs (confidence/cost/time).
export async function fetchStudioQueue() {
  const r = await afetch(`${API_BASE}/api/v1/studio/queue`, { cache: "no-store" });
  if (!r.ok) throw new Error(`studio ${r.status}`);
  return r.json();
}

// Code Memory (codebase-memory-mcp) connector status + indexed projects.
export async function fetchCodeMemory() {
  const r = await afetch(`${LOCAL_BASE}/api/v1/code-memory/status`, { cache: "no-store" });
  if (!r.ok) throw new Error(`code-memory ${r.status}`);
  return r.json();
}

// ── Client Intake — Create New Project ──────────────────────────────────────
export async function fetchProjects() {
  const r = await afetch(`${API_BASE}/api/v1/intake/projects`, { cache: "no-store" });
  if (!r.ok) throw new Error(`projects ${r.status}`); return r.json();
}
export async function createProject(data = {}) {
  const r = await afetch(`${API_BASE}/api/v1/intake/projects`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
  if (!r.ok) throw new Error(`create ${r.status}`); return r.json();
}
export async function fetchProject(id) {
  const r = await afetch(`${API_BASE}/api/v1/intake/projects/${id}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`project ${r.status}`); return r.json();
}
export async function updateProject(id, data, status) {
  const r = await afetch(`${API_BASE}/api/v1/intake/projects/${id}`, {
    method: "PATCH", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ data, status }) });
  if (!r.ok) throw new Error(`update ${r.status}`); return r.json();
}
export async function researchProject(id) {
  const r = await afetch(`${API_BASE}/api/v1/intake/projects/${id}/research`, { method: "POST" });
  if (!r.ok) throw new Error(`research ${r.status}`); return r.json();
}
export async function fetchIntakeForm(token) {
  const r = await afetch(`${API_BASE}/api/v1/intake/form/${token}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`form ${r.status}`); return r.json();
}
export async function submitIntakeForm(token, data) {
  const r = await afetch(`${API_BASE}/api/v1/intake/form/${token}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ data }) });
  if (!r.ok) throw new Error(`submit ${r.status}`); return r.json();
}

// Log in (sets the httponly session cookie so chat/writes are authorized).
export async function setPassword(current, newPassword) {
  const r = await afetch(`${API_BASE}/api/v1/auth/change-password`, {
    method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ current: current || "", new_password: newPassword }) });
  const j = await r.json();
  if (j.token) setSessionToken(j.token);
  return j;
}

export async function login(password, rememberMe = true) {
  const r = await afetch(`${API_BASE}/api/v1/auth/login`, {
    method: "POST", credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password, remember_me: rememberMe }),
  });
  const j = await r.json();
  if (j.token) setSessionToken(j.token);
  return j;   // { ok: true } | { ok: false, error }
}

// Director Library — imported agency Directors (slug/name/description).
export async function fetchDirectors() {
  const r = await afetch(`${API_BASE}/api/v1/directors`, { cache: "no-store" });
  if (!r.ok) throw new Error(`directors ${r.status}`);
  return r.json();
}

// AI Lab — Prompt Library catalog (name · active version · scores).
export async function fetchLabPrompts() {
  const r = await afetch(`${API_BASE}/api/v1/lab/prompts`, { cache: "no-store" });
  if (!r.ok) throw new Error(`lab ${r.status}`);
  return r.json();
}

export async function fetchLabPrompt(name) {
  const r = await afetch(`${API_BASE}/api/v1/lab/prompts/${encodeURIComponent(name)}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`lab ${r.status}`);
  return r.json();
}

export async function rollbackLabPrompt(name, version) {
  const r = await afetch(`${API_BASE}/api/v1/lab/prompts/${encodeURIComponent(name)}/rollback`, {
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
  const r = await afetch(`${LOCAL_BASE}/api/v1/voice/command`, { method: "POST", body: fd });
  if (!r.ok) throw new Error(`voice ${r.status}`);
  return r.json();
}

// Enroll the owner's voice (speaker verification) — records the profile so Saathi
// recognises you. Local-only capability (Mac has the mic + resemblyzer).
export async function enrollVoice(blob) {
  const fd = new FormData();
  fd.append("file", blob, "enroll.webm");
  const r = await afetch(`${LOCAL_BASE}/api/v1/voice/enroll`, { method: "POST", body: fd });
  if (!r.ok) throw new Error(`enroll ${r.status}`);
  return r.json();
}

// Talk to Saathi (the conversation brain). Same-origin cookie auth — the user
// must be logged in on the dashboard. Returns { reply } or throws on 401.
export async function sendChat(text, sessionId = "dashboard") {
  const r = await afetch(`${API_BASE}/api/v1/agent/chat`, {
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
  const r = await afetch(`${API_BASE}/api/v1/studio/plan`, { cache: "no-store" });
  if (!r.ok) throw new Error(`plan ${r.status}`);
  return r.json();
}

// Studio Executive — run the full department pipeline (Research→Creative→Script).
export async function fetchStudioProduce() {
  const r = await afetch(`${API_BASE}/api/v1/studio/produce`, { cache: "no-store" });
  if (!r.ok) throw new Error(`produce ${r.status}`);
  return r.json();
}

// AI Studio OS — the whole content factory in one read (Control Room).
export async function fetchControlRoom() {
  const r = await afetch(`${API_BASE}/api/v1/studio/control-room`, { cache: "no-store" });
  if (!r.ok) throw new Error(`control-room ${r.status}`);
  return r.json();
}

// Production Automation — Credit Manager, Production Plan, approval mode.
export async function fetchAutomationCredits() {
  const r = await afetch(`${API_BASE}/api/v1/automation/credits`, { cache: "no-store" });
  if (!r.ok) throw new Error(`credits ${r.status}`);
  return r.json();
}
export async function fetchProductionPlan() {
  const r = await afetch(`${API_BASE}/api/v1/automation/plan`, { cache: "no-store" });
  if (!r.ok) throw new Error(`plan ${r.status}`);
  return r.json();
}
export async function fetchAutomationSettings() {
  const r = await afetch(`${API_BASE}/api/v1/automation/settings`, { cache: "no-store" });
  if (!r.ok) throw new Error(`settings ${r.status}`);
  return r.json();
}
export async function setApprovalMode(mode) {
  const r = await afetch(`${API_BASE}/api/v1/automation/settings`, {
    method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approval_mode: mode }) });
  if (!r.ok) throw new Error(`mode ${r.status}`);
  return r.json();
}

// Skill Library — reusable skills any Director can find/call.
export async function fetchSkills({ q = "", director = "", category = "" } = {}) {
  const params = new URLSearchParams({ q, director, category });
  const r = await afetch(`${API_BASE}/api/v1/skills?${params}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`skills ${r.status}`);
  return r.json();
}

// Knowledge Library — company-wide sources searchable by every Director.
export async function fetchLibrary({ q = "", category = "", director = "", tag = "" } = {}) {
  const params = new URLSearchParams({ q, category, director, tag });
  const r = await afetch(`${API_BASE}/api/v1/knowledge/library?${params}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`library ${r.status}`);
  return r.json();
}
export async function fetchReadingQueue() {
  const r = await afetch(`${API_BASE}/api/v1/knowledge/queue`, { cache: "no-store" });
  if (!r.ok) throw new Error(`queue ${r.status}`);
  return r.json();
}
export async function importRepo(url, category = "AI Engineering") {
  const r = await afetch(`${API_BASE}/api/v1/knowledge/library/import`, {
    method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, category }) });
  if (!r.ok) throw new Error(`import ${r.status}`);
  return r.json();
}

// Saathi Workspace — one Mission-aware chat that researches/plans/acts (modes).
export async function workspaceTurn(message, mission = "", mode = "cowork") {
  const r = await afetch(`${API_BASE}/api/v1/workspace`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, mission, mode }) });
  if (!r.ok) throw new Error(`workspace ${r.status}`);
  return r.json();
}

// Saathi Workspace — turn an implementation plan into real Mission workflow tasks.
export async function savePlan(mission, name, steps) {
  const r = await afetch(`${API_BASE}/api/v1/workspace/plan/save`, {
    method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mission, name, steps }) });
  if (!r.ok) throw new Error(`save-plan ${r.status}`);
  return r.json();
}

// Connectors — universal account & connector layer.
export async function fetchConnectorProviders() {
  const r = await afetch(`${API_BASE}/api/v1/connectors/providers`, { cache: "no-store" });
  if (!r.ok) throw new Error(`providers ${r.status}`);
  return r.json();
}
export async function fetchAccounts() {
  const r = await afetch(`${API_BASE}/api/v1/connectors/accounts`, { cache: "no-store" });
  if (!r.ok) throw new Error(`accounts ${r.status}`);
  return r.json();
}
export async function addAccount(payload) {
  const r = await afetch(`${API_BASE}/api/v1/connectors/accounts`, {
    method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload) });
  if (!r.ok) throw new Error(`add-account ${r.status}`);
  return r.json();
}
export async function executeConnector(account, capability, params = {}, mission = "") {
  const r = await afetch(`${API_BASE}/api/v1/connectors/execute`, {
    method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ account, capability, params, mission }) });
  if (!r.ok) throw new Error(`execute ${r.status}`);
  return r.json();
}
export async function linkAccountMission(aid, mission, on = true) {
  const r = await afetch(`${API_BASE}/api/v1/connectors/accounts/${aid}/mission`, {
    method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mission, on }) });
  if (!r.ok) throw new Error(`link ${r.status}`);
  return r.json();
}

// Missions — the CEO OS dashboard of every business (Mission = root object).
export async function fetchMissions(status = "") {
  const q = status ? `?status=${status}` : "";
  const r = await afetch(`${API_BASE}/api/v1/missions${q}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`missions ${r.status}`);
  return r.json();
}

// Missions — one Mission's Executive Dashboard (identity + KPIs + evidence + learning + events).
export async function fetchMissionDetail(id) {
  const r = await afetch(`${API_BASE}/api/v1/missions/${id}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`mission ${r.status}`);
  return r.json();
}

// Missions — ＋New Mission: create a Business Digital Twin (research + departments + briefing + roadmap).
export async function createMissionTwin(payload) {
  const r = await afetch(`${API_BASE}/api/v1/missions/twin`, {
    method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new Error(`create-twin ${r.status}`);
  return r.json();
}

// Brand Identity + Voice Registry (voice = reusable per-Mission asset).
export async function fetchBrand(missionId) {
  const r = await afetch(`${API_BASE}/api/v1/missions/${missionId}/brand`, { cache: "no-store" });
  if (!r.ok) throw new Error(`brand ${r.status}`);
  return r.json();
}
export async function registerVoice(missionId, payload) {
  const r = await afetch(`${API_BASE}/api/v1/missions/${missionId}/voices`, {
    method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload) });
  if (!r.ok) throw new Error(`voice ${r.status}`);
  return r.json();
}
export async function activateVoice(missionId, voiceId) {
  const r = await afetch(`${API_BASE}/api/v1/missions/${missionId}/voices/${voiceId}/activate`, {
    method: "POST", credentials: "include" });
  if (!r.ok) throw new Error(`activate ${r.status}`);
  return r.json();
}

// Voice Studio — Voice Director package (provider-agnostic) + A/B experiments.
export async function fetchVoicePackage(missionId, emotion = "", objective = "") {
  const q = new URLSearchParams({ emotion, objective });
  const r = await afetch(`${API_BASE}/api/v1/missions/${missionId}/voice/package?${q}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`voice-package ${r.status}`);
  return r.json();
}
export async function fetchVoiceExperiments(missionId) {
  const r = await afetch(`${API_BASE}/api/v1/missions/${missionId}/voice/experiments`, { cache: "no-store" });
  if (!r.ok) throw new Error(`experiments ${r.status}`);
  return r.json();
}
export async function createVoiceExperiment(missionId, payload) {
  const r = await afetch(`${API_BASE}/api/v1/missions/${missionId}/voice/experiments`, {
    method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload) });
  if (!r.ok) throw new Error(`create-exp ${r.status}`);
  return r.json();
}

// Workflows + Tasks (Director → Workflow → Task).
export async function fetchWorkflows(missionId) {
  const r = await afetch(`${API_BASE}/api/v1/missions/${missionId}/workflows`, { cache: "no-store" });
  if (!r.ok) throw new Error(`workflows ${r.status}`);
  return r.json();
}
export async function createWorkflow(missionId, payload) {
  const r = await afetch(`${API_BASE}/api/v1/missions/${missionId}/workflows`, {
    method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload) });
  if (!r.ok) throw new Error(`create-wf ${r.status}`);
  return r.json();
}
export async function setTaskStatus(missionId, taskId, status) {
  const r = await afetch(`${API_BASE}/api/v1/missions/${missionId}/tasks/${taskId}`, {
    method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }) });
  if (!r.ok) throw new Error(`task ${r.status}`);
  return r.json();
}

// Mission Intake — apply structured onboarding into the Knowledge Graph (no OAuth).
export async function applyIntake(missionId, payload) {
  const r = await afetch(`${API_BASE}/api/v1/missions/${missionId}/intake`, {
    method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload) });
  if (!r.ok) throw new Error(`intake ${r.status}`);
  return r.json();
}
export async function extractDocument(missionId, title, text) {
  const r = await afetch(`${API_BASE}/api/v1/missions/${missionId}/document`, {
    method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title, text }) });
  if (!r.ok) throw new Error(`document ${r.status}`);
  return r.json();
}

// Proposal Director — generate the full Proposal Package from a Mission twin.
export async function generateProposal(missionId) {
  const r = await afetch(`${API_BASE}/api/v1/missions/${missionId}/proposal`, {
    method: "POST", credentials: "include" });
  if (!r.ok) throw new Error(`proposal ${r.status}`);
  return r.json();
}
export async function fetchProposal(missionId) {
  const r = await afetch(`${API_BASE}/api/v1/missions/${missionId}/proposal`, { cache: "no-store" });
  if (!r.ok) throw new Error(`proposal ${r.status}`);
  return r.json();
}
export async function decideProposal(missionId, accept) {
  const r = await afetch(`${API_BASE}/api/v1/missions/${missionId}/proposal/decide`, {
    method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ accept }) });
  if (!r.ok) throw new Error(`decide ${r.status}`);
  return r.json();
}

// Event Bus — volume by type/source + routing table (the spine every product emits to).
export async function fetchEventStats(days = 30) {
  const r = await afetch(`${API_BASE}/api/v1/events/stats?days=${days}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`event-stats ${r.status}`);
  return r.json();
}

// Event Bus — recent events (filter by type glob / source).
export async function fetchEvents({ type = "", source = "", limit = 30 } = {}) {
  const q = new URLSearchParams({ type, source, limit: String(limit) });
  const r = await afetch(`${API_BASE}/api/v1/events?${q}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`events ${r.status}`);
  return r.json();
}

// Learning — run all 3 Learning Directors over the Evidence Store (recommend-only).
export async function runLearningAnalysis() {
  const r = await afetch(`${API_BASE}/api/v1/learning/analyze`, { cache: "no-store" });
  if (!r.ok) throw new Error(`learning-analyze ${r.status}`);
  return r.json();
}

// Learning — list recommendations (searchable by category/status).
export async function fetchRecommendations({ category = "", status = "", limit = 60 } = {}) {
  const q = new URLSearchParams({ category, status, limit: String(limit) });
  const r = await afetch(`${API_BASE}/api/v1/learning/recommendations?${q}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`recommendations ${r.status}`);
  return r.json();
}

// Learning — CEO accepts/rejects a recommendation (nothing auto-changes).
export async function decideRecommendation(id, accept, implemented_in = "") {
  const r = await afetch(`${API_BASE}/api/v1/learning/decide`, {
    method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id, accept, implemented_in }),
  });
  if (!r.ok) throw new Error(`decide ${r.status}`);
  return r.json();
}

// Evidence Service — CEO roll-up across every department (shared memory).
export async function fetchEvidenceStats(days = 30) {
  const r = await afetch(`${API_BASE}/api/v1/evidence/stats?days=${days}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`evidence-stats ${r.status}`);
  return r.json();
}

// Evidence Service — raw query (filter by department/project/episode).
export async function fetchEvidence({ department = "", episode = "", limit = 50 } = {}) {
  const q = new URLSearchParams({ department, episode, limit: String(limit) });
  const r = await afetch(`${API_BASE}/api/v1/evidence?${q}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`evidence ${r.status}`);
  return r.json();
}

// Script Director — generate today's structured episode document.
export async function fetchStudioScript() {
  const r = await afetch(`${API_BASE}/api/v1/studio/script`, { cache: "no-store" });
  if (!r.ok) throw new Error(`script ${r.status}`);
  return r.json();
}

// Today's daily IELTS Mission (lesson topic + checklist + streak).
export async function fetchMission() {
  const r = await afetch(`${API_BASE}/api/v1/mission`, { cache: "no-store" });
  if (!r.ok) throw new Error(`mission ${r.status}`);
  return r.json();
}

// Mark a daily IELTS Mission item done (lesson/speaking/writing/quiz).
export async function completeMission(item) {
  const r = await afetch(`${API_BASE}/api/v1/mission/complete`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ item, done: true }),
  });
  if (!r.ok) throw new Error(`mission ${r.status}`);
  return r.json();
}

// Today's Operating System — one aggregated home-screen call (all real).
export async function fetchCeoOs() {
  const r = await afetch(`${API_BASE}/api/v1/ceo/os`, { cache: "no-store" });
  if (!r.ok) throw new Error(`ceo-os ${r.status}`);
  return r.json();
}

// Platform Maturity — the honest mirror (Infrastructure vs Applications vs Real Data).
export async function fetchMaturity() {
  const r = await afetch(`${API_BASE}/api/v1/platform/maturity`, { cache: "no-store" });
  if (!r.ok) throw new Error(`maturity ${r.status}`);
  return r.json();
}

// Automation Center — status, health score, recent runs (flight recorder).
export async function fetchAutomation() {
  const r = await afetch(`${API_BASE}/api/v1/human/automation`, { cache: "no-store" });
  if (!r.ok) throw new Error(`automation ${r.status}`);
  return r.json();
}

export async function fetchRun(runId) {
  const r = await afetch(`${API_BASE}/api/v1/human/runs/${runId}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`run ${r.status}`);
  return r.json();
}

// Click-to-test the Human Browser Driver end-to-end (token-gated).
export async function testHumanBrowser(token) {
  const r = await afetch(`${API_BASE}/api/v1/human/test`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "x-saathi-token": token || "" },
    body: JSON.stringify({}),
  });
  if (r.status === 401) return { ok: false, error: "unauthorized — wrong SAATHI_TOKEN" };
  return r.json();
}

// ═══════════════════════════════════════════════════════════════════════════════
//  AUTH v1.0 — Session Management, Passkey Management, Forgot Password
// ═══════════════════════════════════════════════════════════════════════════════

export async function logout() {
  const r = await afetch(`${API_BASE}/api/v1/auth/logout`, { method: "POST", credentials: "include" });
  clearSessionToken();
  return r.json();
}

export async function fetchSessions() {
  const r = await afetch(`${API_BASE}/api/v1/auth/sessions`, { cache: "no-store" });
  if (!r.ok) throw new Error(`sessions ${r.status}`);
  return r.json();
}

export async function revokeSession(sid) {
  const r = await afetch(`${API_BASE}/api/v1/auth/sessions/${sid}`, { method: "DELETE", credentials: "include" });
  if (!r.ok) throw new Error(`revoke ${r.status}`);
  return r.json();
}

export async function revokeAllSessions() {
  const r = await afetch(`${API_BASE}/api/v1/auth/sessions/revoke-all`, { method: "POST", credentials: "include" });
  if (!r.ok) throw new Error(`revoke-all ${r.status}`);
  clearSessionToken();
  return r.json();
}

export async function rotateSession() {
  const r = await afetch(`${API_BASE}/api/v1/auth/session/rotate`, { method: "POST", credentials: "include" });
  const j = await r.json();
  if (j.token) setSessionToken(j.token);
  return j;
}

export async function renameSession(sid, label) {
  const r = await afetch(`${API_BASE}/api/v1/auth/sessions/${sid}/rename`, {
    method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ label }),
  });
  if (!r.ok) throw new Error(`rename ${r.status}`);
  return r.json();
}

export async function fetchPasskeys() {
  const r = await afetch(`${API_BASE}/api/v1/auth/passkeys`, { cache: "no-store" });
  if (!r.ok) throw new Error(`passkeys ${r.status}`);
  return r.json();
}

export async function deletePasskey(pid) {
  const r = await afetch(`${API_BASE}/api/v1/auth/passkeys/${pid}`, { method: "DELETE", credentials: "include" });
  if (!r.ok) throw new Error(`delete-passkey ${r.status}`);
  return r.json();
}

export async function renamePasskey(pid, label) {
  const r = await afetch(`${API_BASE}/api/v1/auth/passkeys/${pid}`, {
    method: "PATCH", credentials: "include", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ label }),
  });
  if (!r.ok) throw new Error(`rename-passkey ${r.status}`);
  return r.json();
}

export async function forgotPassword(email) {
  const r = await afetch(`${API_BASE}/api/v1/auth/forgot`, {
    method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  return r.json();
}

export async function resetPassword(token, newPassword) {
  const r = await afetch(`${API_BASE}/api/v1/auth/reset`, {
    method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token, new_password: newPassword }),
  });
  return r.json();
}

export async function fetchAuthAudit(limit = 40) {
  const r = await afetch(`${API_BASE}/api/v1/auth/audit?limit=${limit}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`audit ${r.status}`);
  return r.json();
}

export async function fetchOAuthProviders() {
  const r = await afetch(`${API_BASE}/api/v1/auth/oauth/providers`, { cache: "no-store" });
  if (!r.ok) throw new Error(`oauth ${r.status}`);
  return r.json();
}
