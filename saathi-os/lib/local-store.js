"use client";
// M60 — safe local-only store for NON-SENSITIVE operator workflow state:
// onboarding progress, mission drafts, saved views, notification prefs, search
// history. Never stores tokens, credentials, authority, or secret values — that
// is the server's job. Keys are namespaced under `saathi_m60_*`.

const NS = "saathi_m60_";

export function lsGet(key, fallback) {
  if (typeof window === "undefined") return fallback;
  try {
    const raw = localStorage.getItem(NS + key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

export function lsSet(key, value) {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(NS + key, JSON.stringify(value));
  } catch {
    /* ignore quota/serialization errors */
  }
}

export function lsRemove(key) {
  if (typeof window === "undefined") return;
  try {
    localStorage.removeItem(NS + key);
  } catch {
    /* ignore */
  }
}

export const LS_KEYS = {
  onboarding: "onboarding_progress",
  missionDraft: "mission_draft",
  savedViews: "saved_views",
  notifPrefs: "notification_prefs",
  notifRead: "notification_read",
  searchHistory: "search_history",
};
