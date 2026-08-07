"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { IELTS_NOTICE, ieltsActions } from "@/lib/ielts";
import { getToken } from "@/lib/platform-client.js";

function tokenOf() {
  return getToken() || "";
}

const NAV = [
  "Overview",
  "Onboarding",
  "Diagnostic",
  "Study Plan",
  "Speaking",
  "Writing",
  "Reading",
  "Listening",
  "Mock Test",
  "Readiness",
  "Yeti",
  "Settings",
];

const card = {
  background: "rgba(18,28,48,0.92)",
  border: "1px solid rgba(120,150,200,0.18)",
  borderRadius: 12,
  padding: 14,
};
const btn = {
  background: "#2B6CFF",
  color: "#fff",
  border: "none",
  borderRadius: 8,
  padding: "10px 14px",
  cursor: "pointer",
  fontWeight: 600,
};
const btnGhost = {
  ...btn,
  background: "transparent",
  border: "1px solid rgba(120,150,200,0.35)",
  color: "#D7E2F5",
};

export default function IELTSProductWorkspace() {
  const [token, setToken] = useState("");
  const [view, setView] = useState("Overview");
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [dash, setDash] = useState(null);
  const [examType, setExamType] = useState("academic");
  const [targetBand, setTargetBand] = useState(7);
  const [examDate, setExamDate] = useState("2030-06-01");
  const [dailyMin, setDailyMin] = useState(40);
  const [content, setContent] = useState(null);
  const [diagnostic, setDiagnostic] = useState(null);
  const [plan, setPlan] = useState(null);
  const [readiness, setReadiness] = useState(null);
  const [writingText, setWritingText] = useState("");
  const [speakingText, setSpeakingText] = useState("");
  const [lastSubmission, setLastSubmission] = useState(null);
  const [revisionText, setRevisionText] = useState("");
  const [yetiQ, setYetiQ] = useState("What is my weakest skill?");
  const [yetiA, setYetiA] = useState(null);
  const [mock, setMock] = useState(null);
  const [backup, setBackup] = useState(null);
  const [prepTimer, setPrepTimer] = useState(0);
  const [speakTimer, setSpeakTimer] = useState(0);

  useEffect(() => {
    setToken(tokenOf());
  }, []);

  const refresh = useCallback(async () => {
    const t = tokenOf();
    if (!t) return;
    try {
      const d = await ieltsActions.productDashboard(t);
      setDash(d.dashboard || null);
      const r = await ieltsActions.readiness(t);
      setReadiness(r.data || r.snapshot?.body || null);
    } catch (e) {
      setError(e.message || "Load failed");
    }
  }, []);

  useEffect(() => {
    if (token) refresh();
  }, [token, refresh]);

  async function run(fn) {
    setBusy(true);
    setError("");
    setStatus("");
    try {
      await fn();
      await refresh();
    } catch (e) {
      setError(e.message || "Action failed");
    } finally {
      setBusy(false);
    }
  }

  if (!token) {
    return (
      <main style={{ padding: 24, color: "#E8EEF9" }} aria-label="IELTSAlert product workspace">
        <h1>IELTSAlert</h1>
        <p>Sign in required.</p>
        <Link href="/security">Go to Security</Link>
      </main>
    );
  }

  const ready = readiness || dash?.readiness || {};

  return (
    <main
      style={{
        minHeight: "100vh",
        background: "linear-gradient(160deg,#0B1220,#121C30)",
        color: "#E8EEF9",
        padding: "16px 16px 48px",
      }}
      aria-label="IELTSAlert product workspace"
    >
      <header style={{ display: "flex", flexWrap: "wrap", gap: 12, marginBottom: 12 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22 }}>IELTSAlert · AI Coaching</h1>
          <p style={{ margin: "4px 0 0", color: "#8B98B4", fontSize: 13 }}>
            {IELTS_NOTICE.scoring} Local-only · {IELTS_NOTICE.payment}
          </p>
        </div>
        <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          <Link href="/apps" style={{ color: "#9EC1FF" }}>
            Application launcher
          </Link>
          <Link href="/ielts" style={{ color: "#9EC1FF" }}>
            Classic workspace
          </Link>
        </div>
      </header>

      <nav aria-label="IELTSAlert sections" style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 12 }}>
        {NAV.map((n) => (
          <button
            key={n}
            type="button"
            style={{
              ...btnGhost,
              background: view === n ? "rgba(43,108,255,0.25)" : "transparent",
              borderColor: view === n ? "#2B6CFF" : "rgba(120,150,200,0.35)",
            }}
            aria-current={view === n ? "page" : undefined}
            onClick={() => setView(n)}
          >
            {n}
          </button>
        ))}
      </nav>

      <div aria-live="polite" style={{ minHeight: 22, color: error ? "#FF8A8A" : "#10C98A", marginBottom: 8 }}>
        {error || status}
      </div>

      {view === "Overview" && (
        <section style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit,minmax(160px,1fr))" }}>
          {[
            ["Practice count", dash?.progress?.practice_count ?? "—"],
            ["Overall estimate", ready.overall_estimate ?? "—"],
            ["Target band", ready.target_band ?? "—"],
            ["Weakest skill", ready.weakest_skill ?? "—"],
            ["Readiness", ready.readiness_label ?? "—"],
            ["Confidence", ready.confidence_label ?? "—"],
            ["Study plans", dash?.study_plan_count ?? 0],
            ["Mock tests", dash?.mock_test_count ?? 0],
          ].map(([k, v]) => (
            <div key={k} style={card}>
              <div style={{ color: "#8B98B4", fontSize: 12 }}>{k}</div>
              <div style={{ fontSize: 18, fontWeight: 700, marginTop: 6 }}>{String(v)}</div>
            </div>
          ))}
          <div style={{ ...card, gridColumn: "1 / -1" }}>
            <strong>Scoring posture:</strong> estimates only · rubric versions preserved · no live Gemini · no official IELTS claim
          </div>
        </section>
      )}

      {view === "Onboarding" && (
        <section style={card}>
          <h2 style={{ marginTop: 0 }}>Learner profile & goal</h2>
          <div style={{ display: "grid", gap: 10, maxWidth: 480 }}>
            <label>
              Exam type
              <select value={examType} onChange={(e) => setExamType(e.target.value)} style={{ width: "100%", marginTop: 4, padding: 8 }} aria-label="Exam type">
                <option value="academic">Academic</option>
                <option value="general_training">General Training</option>
              </select>
            </label>
            <label>
              Target band
              <input type="number" step="0.5" min="4" max="9" value={targetBand} onChange={(e) => setTargetBand(Number(e.target.value))} style={{ width: "100%", marginTop: 4, padding: 8 }} aria-label="Target band" />
            </label>
            <label>
              Exam date
              <input type="date" value={examDate} onChange={(e) => setExamDate(e.target.value)} style={{ width: "100%", marginTop: 4, padding: 8 }} aria-label="Exam date" />
            </label>
            <label>
              Daily minutes
              <input type="number" value={dailyMin} onChange={(e) => setDailyMin(Number(e.target.value))} style={{ width: "100%", marginTop: 4, padding: 8 }} aria-label="Daily study minutes" />
            </label>
            <button
              type="button"
              style={btn}
              disabled={busy}
              onClick={() =>
                run(async () => {
                  await ieltsActions.profile({ display_name: "Certification Learner" }, token);
                  await ieltsActions.goal(
                    {
                      exam_type: examType,
                      target_band: targetBand,
                      planned_test_date: examDate,
                      daily_minutes: dailyMin,
                      idempotency_key: `goal-${examType}-${targetBand}`,
                    },
                    token
                  );
                  setStatus("Profile and goal saved");
                })
              }
            >
              Save profile & goal
            </button>
          </div>
        </section>
      )}

      {view === "Diagnostic" && (
        <section style={card}>
          <h2 style={{ marginTop: 0 }}>Diagnostic assessment</h2>
          <p style={{ color: "#8B98B4" }}>Short synthetic four-skill diagnostic. Estimates only.</p>
          <button
            type="button"
            style={btn}
            disabled={busy}
            onClick={() =>
              run(async () => {
                const r = await ieltsActions.diagnostic(
                  { exam_type: examType, idempotency_key: `diag-${examType}-${Date.now()}` },
                  token
                );
                setDiagnostic(r.diagnostic);
                setStatus(`Diagnostic complete · overall ${r.diagnostic?.body?.overall_estimate}`);
              })
            }
          >
            Run diagnostic
          </button>
          {diagnostic && (
            <pre style={{ marginTop: 12, fontSize: 12, overflow: "auto", background: "#0B1220", padding: 12, borderRadius: 8 }}>
              {JSON.stringify(diagnostic.body?.skill_estimates || diagnostic.body, null, 2)}
            </pre>
          )}
        </section>
      )}

      {view === "Study Plan" && (
        <section style={card}>
          <h2 style={{ marginTop: 0 }}>Personalized study plan</h2>
          <button
            type="button"
            style={btn}
            disabled={busy}
            onClick={() =>
              run(async () => {
                const r = await ieltsActions.studyPlan({ weeks: 4, idempotency_key: `plan-${Date.now()}` }, token);
                setPlan(r.plan);
                setStatus("Study plan generated and validated");
              })
            }
          >
            Generate 4-week plan
          </button>
          {plan && (
            <div style={{ marginTop: 12 }}>
              <p>
                Tasks: {(plan.body?.tasks || []).length} · total minutes {plan.body?.total_minutes} · weak focus{" "}
                {plan.body?.weakest_skill}
              </p>
              <p style={{ color: "#8B98B4", fontSize: 13 }}>
                Validation: {JSON.stringify(plan.body?.validation)} · PlanValidator: {plan.body?.plan_validator}
              </p>
            </div>
          )}
        </section>
      )}

      {view === "Speaking" && (
        <section style={card}>
          <h2 style={{ marginTop: 0 }}>Speaking practice</h2>
          <p style={{ color: "#8B98B4" }}>Text-transcript certification path. Pronunciation is not acoustically assessed.</p>
          <button
            type="button"
            style={btnGhost}
            onClick={() =>
              run(async () => {
                const c = await ieltsActions.content(examType, token);
                setContent(c);
                setPrepTimer(c.speaking?.[1]?.prep_seconds || 60);
                setSpeakTimer(c.speaking?.[1]?.response_seconds || 120);
                setStatus("Part 2 prompt loaded · timers ready");
              })
            }
          >
            Load Part 2 prompt + timers
          </button>
          {content?.speaking?.[1] && (
            <p style={{ marginTop: 10 }}>
              <strong>Prompt:</strong> {content.speaking[1].prompt}
            </p>
          )}
          <p style={{ fontSize: 13 }}>
            Prep timer: {prepTimer}s · Speak timer: {speakTimer}s
          </p>
          <textarea
            value={speakingText}
            onChange={(e) => setSpeakingText(e.target.value)}
            rows={5}
            style={{ width: "100%", marginTop: 8, padding: 8, borderRadius: 8 }}
            aria-label="Speaking transcript"
            placeholder="Paste or type speaking transcript (synthetic OK)"
          />
          <button
            type="button"
            style={{ ...btn, marginTop: 8 }}
            disabled={busy || !speakingText.trim()}
            onClick={() =>
              run(async () => {
                const r = await ieltsActions.practice(
                  {
                    skill: "speaking",
                    task_type: "part_2",
                    prompt: content?.speaking?.[1]?.prompt || "Describe a journey.",
                    response: speakingText,
                    duration_seconds: 120,
                    idempotency_key: `sp-${Date.now()}`,
                  },
                  token
                );
                setLastSubmission(r.practice);
                setStatus(
                  `Speaking feedback: ${r.practice?.body?.feedback?.overall_level} · pronunciation=${r.practice?.body?.feedback?.criteria?.pronunciation?.level}`
                );
              })
            }
          >
            Submit speaking (text)
          </button>
        </section>
      )}

      {view === "Writing" && (
        <section style={card}>
          <h2 style={{ marginTop: 0 }}>Writing Task practice</h2>
          <textarea
            value={writingText}
            onChange={(e) => setWritingText(e.target.value)}
            rows={8}
            style={{ width: "100%", padding: 8, borderRadius: 8 }}
            aria-label="Writing response"
            placeholder="Write Task 2 essay response…"
          />
          <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
            <button
              type="button"
              style={btn}
              disabled={busy || !writingText.trim()}
              onClick={() =>
                run(async () => {
                  const r = await ieltsActions.practice(
                    {
                      skill: "writing",
                      task_type: examType === "general_training" ? "task_2" : "task_2",
                      prompt:
                        examType === "general_training"
                          ? "Some people believe public libraries are no longer necessary because of the internet."
                          : "Universities should focus more on practical skills than theoretical knowledge.",
                      response: writingText,
                      duration_seconds: 2400,
                      idempotency_key: `wr-${Date.now()}`,
                    },
                    token
                  );
                  setLastSubmission(r.practice);
                  setStatus(`Writing estimate band ${r.practice?.body?.feedback?.estimated_overall_band}`);
                })
              }
            >
              Submit writing (immutable)
            </button>
          </div>
          {lastSubmission?.record_type === "submission" && (
            <div style={{ marginTop: 12 }}>
              <p>Submission {lastSubmission.record_id} locked. Create a revision:</p>
              <textarea
                value={revisionText}
                onChange={(e) => setRevisionText(e.target.value)}
                rows={4}
                style={{ width: "100%", padding: 8, borderRadius: 8 }}
                aria-label="Writing revision"
              />
              <button
                type="button"
                style={{ ...btnGhost, marginTop: 8 }}
                disabled={busy || !revisionText.trim()}
                onClick={() =>
                  run(async () => {
                    const r = await ieltsActions.writingRevision(
                      {
                        parent_submission_id: lastSubmission.record_id,
                        response: revisionText,
                        idempotency_key: `rev-${Date.now()}`,
                      },
                      token
                    );
                    setStatus(`Revision linked to ${r.parent_id} · parent_immutable=${r.parent_immutable}`);
                  })
                }
              >
                Submit revision
              </button>
            </div>
          )}
        </section>
      )}

      {view === "Reading" && (
        <section style={card}>
          <h2 style={{ marginTop: 0 }}>Reading practice</h2>
          <button
            type="button"
            style={btn}
            disabled={busy}
            onClick={() =>
              run(async () => {
                const c = await ieltsActions.content(examType, token);
                setContent(c);
                const answers = (c.reading?.questions || []).map((q) => q.answer);
                const r = await ieltsActions.objectivePractice(
                  {
                    skill: "reading",
                    exam_type: examType,
                    answers,
                    idempotency_key: `rd-${Date.now()}`,
                  },
                  token
                );
                setStatus(
                  `Reading ${r.practice?.body?.feedback?.correct}/${r.practice?.body?.feedback?.total} · band ${r.practice?.body?.feedback?.estimated_overall_band}`
                );
              })
            }
          >
            Load fixture & submit correct answers
          </button>
        </section>
      )}

      {view === "Listening" && (
        <section style={card}>
          <h2 style={{ marginTop: 0 }}>Listening practice</h2>
          <p style={{ color: "#8B98B4" }}>Text transcript fixture — no certified acoustic engine.</p>
          <button
            type="button"
            style={btn}
            disabled={busy}
            onClick={() =>
              run(async () => {
                const c = await ieltsActions.content(examType, token);
                const answers = (c.listening?.questions || []).map((q) => q.answer);
                const r = await ieltsActions.objectivePractice(
                  {
                    skill: "listening",
                    exam_type: examType,
                    answers,
                    idempotency_key: `ls-${Date.now()}`,
                  },
                  token
                );
                setStatus(
                  `Listening ${r.practice?.body?.feedback?.correct}/${r.practice?.body?.feedback?.total} · modality=${c.listening?.modality}`
                );
              })
            }
          >
            Complete listening fixture
          </button>
        </section>
      )}

      {view === "Mock Test" && (
        <section style={card}>
          <h2 style={{ marginTop: 0 }}>Mock test workflow</h2>
          <button
            type="button"
            style={btn}
            disabled={busy}
            onClick={() =>
              run(async () => {
                const m = await ieltsActions.mockTest(
                  { exam_type: examType, idempotency_key: `mock-${Date.now()}` },
                  token
                );
                setMock(m.mock_test);
                await ieltsActions.mockSection(m.mock_test.record_id, { skill: "listening", answers: ["second", "10", "17:00", "true"] }, token);
                await ieltsActions.mockSection(m.mock_test.record_id, { skill: "reading", answers: ["false", "20", "true", "flowering plants"] }, token);
                await ieltsActions.mockSection(m.mock_test.record_id, { skill: "writing", response: "Mock essay with structure and examples. ".repeat(20) }, token);
                await ieltsActions.mockSection(m.mock_test.record_id, { skill: "speaking", response: "Mock speaking answer with reasons and examples." }, token);
                setStatus("Mock sections completed");
              })
            }
          >
            Start & complete mock sections
          </button>
          {mock && <p style={{ marginTop: 8 }}>Mock {mock.record_id}</p>}
        </section>
      )}

      {view === "Readiness" && (
        <section style={card}>
          <h2 style={{ marginTop: 0 }}>Exam readiness</h2>
          <button type="button" style={btn} disabled={busy} onClick={() => run(async () => {
            const r = await ieltsActions.readiness(token);
            setReadiness(r.data);
            setStatus(`Readiness ${r.data?.readiness_label}`);
          })}>
            Refresh readiness
          </button>
          {ready && (
            <pre style={{ marginTop: 12, fontSize: 12, overflow: "auto", background: "#0B1220", padding: 12, borderRadius: 8 }}>
              {JSON.stringify(ready, null, 2)}
            </pre>
          )}
        </section>
      )}

      {view === "Yeti" && (
        <section style={card}>
          <h2 style={{ marginTop: 0 }}>Ask Yeti (grounded, read-only)</h2>
          <div style={{ display: "flex", gap: 8 }}>
            <input
              value={yetiQ}
              onChange={(e) => setYetiQ(e.target.value)}
              style={{ flex: 1, padding: 8, borderRadius: 8 }}
              aria-label="Yeti coaching question"
            />
            <button
              type="button"
              style={btn}
              disabled={busy}
              onClick={() =>
                run(async () => {
                  const a = await ieltsActions.yeti(yetiQ, token);
                  setYetiA(a);
                })
              }
            >
              Ask
            </button>
          </div>
          {yetiA && (
            <div style={{ marginTop: 10 }}>
              <p>{yetiA.answer}</p>
              <p style={{ fontSize: 12, color: "#8B98B4" }}>
                can_mutate={String(yetiA.can_mutate)} · official={String(yetiA.official)}
              </p>
            </div>
          )}
        </section>
      )}

      {view === "Settings" && (
        <section style={card}>
          <h2 style={{ marginTop: 0 }}>Backup · reminders · health</h2>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button
              type="button"
              style={btn}
              onClick={() =>
                run(async () => {
                  const b = await ieltsActions.backup(token);
                  setBackup(b.backup);
                  setStatus(`Backup hash ${b.backup?.content_hash?.slice(0, 12)}…`);
                })
              }
            >
              Backup progress
            </button>
            <button
              type="button"
              style={btnGhost}
              disabled={!backup}
              onClick={() =>
                run(async () => {
                  try {
                    await ieltsActions.restore({ payload: backup, approval_reference: "" }, token);
                  } catch (e) {
                    setStatus(`Restore gated: ${e.message}`);
                    throw e;
                  }
                })
              }
            >
              Restore (requires approval)
            </button>
            <button
              type="button"
              style={btnGhost}
              onClick={() =>
                run(async () => {
                  await ieltsActions.reminder(
                    { title: "Daily writing practice", due_date: examDate, kind: "study" },
                    token
                  );
                  setStatus("Reminder created");
                })
              }
            >
              Create study reminder
            </button>
          </div>
          <p style={{ marginTop: 12, color: "#8B98B4", fontSize: 13 }}>
            Production not authorized · No Firebase · No live Gemini · {IELTS_NOTICE.availability}
          </p>
        </section>
      )}
    </main>
  );
}
