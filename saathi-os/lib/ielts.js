"use client";
import { useCallback, useEffect, useState } from "react";
import { getToken, plat, PLATFORM_CONTEXT_EVENT } from "./platform-client.js";

export const IELTS_NOTICE = {
  scoring: "Practice estimates only — never official IELTS scores.",
  availability: "Availability uses labelled local fixtures, not live test-center data.",
  payment: "Manual verification only — no payment settlement is performed.",
};

const boundedSpeechText = (value, maximum = 500) =>
  String(value || "").replace(/\s+/g, " ").trim().slice(0, maximum);

export function ieltsFeedbackSpeech(record) {
  const feedback = record?.body?.feedback;
  if (!feedback || typeof feedback !== "object") return "";
  const parts = [
    `IELTS ${boundedSpeechText(feedback.label || "practice feedback", 80)}.`,
  ];
  if (feedback.overall_level) {
    parts.push(
      `Overall practice level: ${boundedSpeechText(feedback.overall_level, 80)}.`
    );
  } else if (Number.isFinite(Number(feedback.answers_recorded))) {
    parts.push(`${Number(feedback.answers_recorded)} answers were recorded.`);
  }
  for (const [criterion, value] of Object.entries(feedback.criteria || {})) {
    const title = boundedSpeechText(criterion.replaceAll("_", " "), 80);
    const level = boundedSpeechText(value?.level, 80);
    const note = boundedSpeechText(value?.feedback, 500);
    if (title && (level || note)) {
      parts.push(`${title}.${level ? ` Level ${level}.` : ""}${note ? ` ${note}` : ""}`);
    }
  }
  const limitations = Array.isArray(feedback.limitations)
    ? feedback.limitations.map((item) => boundedSpeechText(item, 300)).filter(Boolean)
    : [];
  if (limitations.length) parts.push(`Limitations. ${limitations.join(" ")}`);
  parts.push("This is practice feedback, never an official IELTS score.");
  return parts.join(" ").slice(0, 4_000);
}

export async function ielts(path, { method = "GET", body, token, signal } = {}) {
  return plat(`/ielts${path}`, { method, body, token: token || getToken(), signal });
}

export const ieltsActions = {
  profile: (body, token) => ielts("/profile", { method: "POST", body, token }),
  goal: (body, token) => ielts("/goals", { method: "POST", body, token }),
  practice: (body, token) => ielts("/practice", { method: "POST", body, token }),
  alert: (body, token) => ielts("/alerts", { method: "POST", body, token }),
  evaluateAlerts: (token) => ielts("/alerts/evaluate", { method: "POST", token }),
  payment: (body, token) => ielts("/payments", { method: "POST", body, token }),
  reviewPayment: (id, body, token) => ielts(`/payments/${encodeURIComponent(id)}/review`, { method: "POST", body, token }),
  productDashboard: (token) => ielts("/product-dashboard", { token }),
  content: (examType, token) => ielts(`/content?exam_type=${encodeURIComponent(examType || "academic")}`, { token }),
  diagnostic: (body, token) => ielts("/diagnostic", { method: "POST", body, token }),
  studyPlan: (body, token) => ielts("/study-plan", { method: "POST", body, token }),
  objectivePractice: (body, token) => ielts("/objective-practice", { method: "POST", body, token }),
  writingRevision: (body, token) => ielts("/writing/revision", { method: "POST", body, token }),
  mockTest: (body, token) => ielts("/mock-tests", { method: "POST", body, token }),
  mockSection: (id, body, token) => ielts(`/mock-tests/${encodeURIComponent(id)}/sections`, { method: "POST", body, token }),
  readiness: (token) => ielts("/readiness", { token }),
  yeti: (question, token) => ielts("/yeti", { method: "POST", body: { question }, token }),
  backup: (token) => ielts("/backup", { method: "POST", token }),
  restore: (body, token) => ielts("/restore", { method: "POST", body, token }),
  reminder: (body, token) => ielts("/reminders", { method: "POST", body, token }),
};

const EMPTY = { dashboard: null, records: [], evidence: [], permissions: [], userId: "" };

export function useIELTSData({ allOwners = false } = {}) {
  const [token, setToken] = useState("");
  const [data, setData] = useState(EMPTY);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const refresh = useCallback(async (explicitToken) => {
    const active = explicitToken ?? getToken();
    setToken(active);
    if (!active) {
      setData(EMPTY); setLoading(false); setError(null); return;
    }
    setLoading(true); setError(null);
    try {
      const suffix = allOwners ? "?all_owners=true" : "";
      const [me, dashboard, records, evidence] = await Promise.all([
        plat("/me", { token: active }),
        ielts("/dashboard", { token: active }),
        ielts(`/records${suffix}`, { token: active }),
        ielts(`/evidence${suffix}`, { token: active }),
      ]);
      setData({
        dashboard: dashboard.dashboard || null,
        records: records.records || [],
        evidence: evidence.evidence || [],
        permissions: me.permissions || [],
        userId: me.user?.user_id || "",
      });
    } catch (e) {
      setData(EMPTY);
      setError({ status: e?.status || 0, message: String(e?.message || e) });
    } finally {
      setLoading(false);
    }
  }, [allOwners]);

  useEffect(() => {
    refresh();
    const onContext = (event) => {
      setData(EMPTY); setLoading(true);
      refresh(event?.detail?.token ?? getToken());
    };
    window.addEventListener(PLATFORM_CONTEXT_EVENT, onContext);
    return () => window.removeEventListener(PLATFORM_CONTEXT_EVENT, onContext);
  }, [refresh]);

  return { token, loading, error, refresh, ...data };
}
