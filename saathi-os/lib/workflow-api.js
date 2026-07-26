"use client";
// M61 — client adapter for the server-authoritative workflow persistence APIs.
// The browser becomes thinner: plans, notifications, saved views, templates,
// drafts, attention mutations, and search now round-trip to the server. Each
// call is optimistic-concurrency aware (pass expected_version; a 409 surfaces a
// STALE_STATE conflict the UI must reconcile).
import { plat } from "./platform-client";

// ── plans ──
export const getPlan = (missionId, token) => plat(`/workflow/plans/${encodeURIComponent(missionId)}`, { token }).then((r) => r.plan);
export const upsertPlan = (missionId, body, token, expectedVersion) =>
  plat("/workflow/plans", { method: "PUT", token, body: { mission_id: missionId, body, expected_version: expectedVersion ?? undefined } }).then((r) => r.plan);
export const publishPlan = (missionId, expectedVersion, token) =>
  plat("/workflow/plans/publish", { method: "POST", token, body: { mission_id: missionId, expected_version: expectedVersion } }).then((r) => r.plan);

// ── notifications ──
export const listNotifications = (token, includeArchived = false) =>
  plat(`/workflow/notifications?include_archived=${includeArchived ? 1 : 0}`, { token }).then((r) => r.notifications || []);
export const createNotification = (n, token) => plat("/workflow/notifications", { method: "POST", token, body: n }).then((r) => r.notification);
export const flagNotification = (id, flags, token) => plat(`/workflow/notifications/${id}`, { method: "PATCH", token, body: flags }).then((r) => r.notification);

// ── saved views ──
export const listViews = (token) => plat("/workflow/saved-views", { token }).then((r) => r.views || []);
export const createView = (v, token) => plat("/workflow/saved-views", { method: "POST", token, body: v }).then((r) => r.view);
export const updateView = (id, patch, token) => plat(`/workflow/saved-views/${id}`, { method: "PATCH", token, body: patch }).then((r) => r.view);
export const deleteView = (id, token) => plat(`/workflow/saved-views/${id}`, { method: "DELETE", token });

// ── templates ──
export const listServerTemplates = (token) => plat("/workflow/templates", { token }).then((r) => r.templates || []);
export const createTemplate = (t, token) => plat("/workflow/templates", { method: "POST", token, body: t }).then((r) => r.template);

// ── drafts ──
export const getDraft = (kind, token) => plat(`/workflow/drafts/${kind}`, { token }).then((r) => r.draft);
export const saveDraft = (kind, body, token) => plat("/workflow/drafts", { method: "PUT", token, body: { kind, body } }).then((r) => r.draft);
export const discardDraft = (kind, token) => plat(`/workflow/drafts/${kind}`, { method: "DELETE", token });

// ── attention mutations ──
export const attentionState = (execId, token) => plat(`/workflow/attention/${encodeURIComponent(execId)}/state`, { token }).then((r) => r.attention);
export const attentionAction = (execId, action, token, { note = "", expectedVersion } = {}) =>
  plat(`/workflow/attention/${encodeURIComponent(execId)}/action`, { method: "POST", token, body: { action, note, expected_version: expectedVersion ?? undefined } }).then((r) => r.attention);

// ── server search ──
export const serverSearch = (q, token, { type = "all", limit = 50 } = {}) =>
  plat(`/workflow/search?q=${encodeURIComponent(q)}&type=${type}&limit=${limit}`, { token });

/* Is an error an optimistic-concurrency conflict? */
export const isConflict = (e) => e?.status === 409 || /STALE_STATE|conflict/i.test(String(e?.message || e));
