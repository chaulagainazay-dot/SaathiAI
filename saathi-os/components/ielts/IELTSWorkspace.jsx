"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Button, Card, EmptyState, ErrorState, Heading, Spinner, Text } from "@/components/ui";
import { IELTS_NOTICE, ieltsActions, useIELTSData } from "@/lib/ielts";

const TABS = [
  ["/ielts", "Dashboard"], ["/ielts/onboarding", "Profile"], ["/ielts/goals", "Goal"],
  ["/ielts/practice", "Practice"], ["/ielts/submissions", "Feedback"],
  ["/ielts/alerts", "Alerts"], ["/ielts/payments", "Payments"],
  ["/ielts/evidence", "Evidence"], ["/ielts/settings", "Settings"],
];

const field = {
  width: "100%", boxSizing: "border-box", padding: "9px 10px", borderRadius: 8,
  color: "var(--text-primary)", background: "var(--surface-subtle)",
  border: "1px solid var(--border)", marginTop: 4,
};
const grid = { display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(240px,1fr))", gap: 12 };

function Banner({ children, tone = "info" }) {
  const color = tone === "warn" ? "var(--status-warning,#F5A623)" : "var(--accent,#5B8CFF)";
  return <div role="note" style={{ padding: "9px 12px", borderRadius: 8, border: `1px solid ${color}`,
    color: "var(--text-secondary)", marginBottom: 12, fontSize: 12 }}>{children}</div>;
}

function Field({ label, children }) {
  return <label style={{ display: "block", color: "var(--text-secondary)", fontSize: 12 }}>{label}{children}</label>;
}

function RecordList({ records, empty = "Nothing here yet." }) {
  if (!records.length) return <EmptyState title={empty} />;
  return <div style={{ display: "grid", gap: 8 }}>{records.map((r) => (
    <Card key={r.record_id} style={{ padding: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <Text weight={600}>{r.body?.skill ? `${r.body.skill} · ${r.body.task_type}` : r.record_type}</Text>
        <span className="mono" style={{ fontSize: 11, color: "var(--text-muted)" }}>{r.status}</span>
      </div>
      {r.body?.feedback && <Text as="p" tone="muted" size="sm" style={{ marginTop: 6 }}>
        {r.body.feedback.label}: {r.body.feedback.overall_level || `${r.body.feedback.answers_recorded || 0} answers recorded`}
      </Text>}
      {r.body?.disclaimer && <Text as="p" tone="muted" size="xs">{r.body.disclaimer}</Text>}
    </Card>
  ))}</div>;
}

function WorkspaceHeader() {
  const pathname = usePathname() || "/ielts";
  return <>
    <header style={{ marginBottom: 14 }}>
      <Text tone="muted" size="xs" mono>Applications · IELTSAlert · Local practice</Text>
      <Heading level={1} size="2xl">IELTSAlert</Heading>
      <Text as="p" tone="muted" size="sm">A bounded preparation workspace with transparent practice feedback and local alerts.</Text>
    </header>
    <nav aria-label="IELTSAlert workspace" style={{ display: "flex", gap: 4, flexWrap: "wrap",
      borderBottom: "1px solid var(--border)", paddingBottom: 8, marginBottom: 16 }}>
      {TABS.map(([href, label]) => {
        const active = href === "/ielts" ? pathname === href : pathname.startsWith(href);
        return <Link key={href} href={href} aria-current={active ? "page" : undefined}
          style={{ padding: "6px 10px", borderRadius: 7, textDecoration: "none", fontSize: 12,
            color: active ? "var(--text-primary)" : "var(--text-muted)",
            background: active ? "var(--surface-hover)" : "transparent" }}>{label}</Link>;
      })}
    </nav>
  </>;
}

function FormStatus({ busy, message, error }) {
  return <div aria-live="polite" role={error ? "alert" : "status"} style={{
    minHeight: 20, marginTop: 8, fontSize: 12,
    color: error ? "var(--status-danger)" : "var(--text-muted)",
  }}>{busy ? "Saving…" : error || message}</div>;
}

export default function IELTSWorkspace({ view = "dashboard" }) {
  const d = useIELTSData({ allOwners: view === "payments" });
  const router = useRouter();
  const pathname = usePathname() || "/ielts";
  const routeSkill = ["reading", "listening", "writing", "speaking"]
    .find((skill) => pathname.endsWith(`/practice/${skill}`)) || "reading";
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [formError, setFormError] = useState("");

  const act = async (fn, success) => {
    setBusy(true); setFormError(""); setMessage("");
    try {
      await fn();
      setMessage(success);
      await d.refresh(d.token);
    } catch (e) {
      setFormError(`${e?.status || "Error"}: ${e?.message || e}`);
    } finally { setBusy(false); }
  };

  if (!d.token && !d.loading) return <main className="page shell-page"><WorkspaceHeader />
    <Card style={{ maxWidth: 560 }}><Heading level={2}>Sign in required</Heading>
      <Text as="p" tone="muted">Select an organization and workspace before opening IELTSAlert.</Text>
      <Button onClick={() => router.push("/unlock")}>Sign in</Button></Card></main>;

  const body = {
    dashboard: <Dashboard d={d} />,
    onboarding: <ProfileForm act={act} busy={busy} />,
    goals: <GoalForm act={act} busy={busy} records={d.records} />,
    practice: <PracticeForm act={act} busy={busy} initialSkill={routeSkill} />,
    submissions: <FeedbackView records={d.records} />,
    alerts: <AlertsView act={act} busy={busy} records={d.records} token={d.token} />,
    payments: <PaymentsView act={act} busy={busy} records={d.records} token={d.token}
      permissions={d.permissions} userId={d.userId} />,
    evidence: <EvidenceView evidence={d.evidence} />,
    settings: <SettingsView />,
  }[view] || <Dashboard d={d} />;

  return <main className="page shell-page" style={{ maxWidth: 1120, margin: "0 auto" }}>
    <WorkspaceHeader />
    <Banner>{IELTS_NOTICE.scoring}</Banner>
    {d.loading ? <div style={{ padding: 40, textAlign: "center" }} role="status"><Spinner size={22} /> Loading IELTSAlert…</div> : null}
    {d.error ? <ErrorState title={d.error.status === 403 ? "Permission restricted" : "Could not load IELTSAlert"}
      detail={d.error.message} action={<Button onClick={() => d.refresh()}>Retry</Button>} /> : null}
    {!d.loading && !d.error ? body : null}
    <FormStatus busy={busy} message={message} error={formError} />
  </main>;
}

function Dashboard({ d }) {
  const x = d.dashboard;
  if (!x) return <EmptyState title="Your IELTS dashboard is not ready yet." />;
  const goal = x.goal?.body;
  return <>
    {!goal && <Banner tone="warn">No exam goal yet. Start with Profile and Goal.</Banner>}
    <section aria-label="Preparation summary" style={grid}>
      <Metric label="Target band" value={goal?.target_band || "Not set"} />
      <Metric label="Planned test" value={goal?.planned_test_date || "Not set"} />
      <Metric label="Practice records" value={x.progress.practice_count} />
      <Metric label="Next practice" value={x.next_practice} />
      <Metric label="Active alerts" value={x.active_alerts} />
      <Metric label="Pending payment review" value={x.pending_payments} />
    </section>
    <Card style={{ marginTop: 14 }}><Heading level={2} size="md">Practice balance</Heading>
      <div style={{ ...grid, marginTop: 10 }}>{Object.entries(x.progress.by_skill).map(([skill, count]) =>
        <div key={skill}><Text tone="muted" size="sm">{skill}</Text><Heading level={3}>{count}</Heading></div>)}</div>
    </Card>
  </>;
}
function Metric({ label, value }) {
  return <Card><Text tone="muted" size="xs" mono>{label}</Text><Heading level={2} size="xl" style={{ marginTop: 5 }}>{value}</Heading></Card>;
}

function ProfileForm({ act, busy }) {
  const [name, setName] = useState("");
  return <Card><Heading level={2}>Learner profile</Heading><form onSubmit={(e) => {
    e.preventDefault(); act(() => ieltsActions.profile({ display_name: name, timezone: "Asia/Kathmandu" }), "Profile saved.");
  }} style={{ ...grid, marginTop: 12 }}>
    <Field label="Display name"><input required maxLength={100} value={name} onChange={(e) => setName(e.target.value)} style={field} /></Field>
    <div style={{ alignSelf: "end" }}><Button disabled={busy} type="submit">Save profile</Button></div>
  </form></Card>;
}

function GoalForm({ act, busy, records }) {
  const [exam, setExam] = useState("academic"), [band, setBand] = useState("7.0"), [date, setDate] = useState("2030-02-01");
  const goals = records.filter((r) => r.record_type === "goal");
  return <div style={{ display: "grid", gap: 14 }}><Card><Heading level={2}>Exam goal</Heading>
    <form onSubmit={(e) => { e.preventDefault(); act(() => ieltsActions.goal({
      exam_type: exam, target_band: Number(band), planned_test_date: date, daily_minutes: 30,
      idempotency_key: `goal-${exam}-${band}-${date}`,
    }), "Exam goal saved."); }} style={{ ...grid, marginTop: 12 }}>
      <Field label="IELTS type"><select value={exam} onChange={(e) => setExam(e.target.value)} style={field}>
        <option value="academic">Academic</option><option value="general_training">General Training</option></select></Field>
      <Field label="Target band"><select value={band} onChange={(e) => setBand(e.target.value)} style={field}>
        {["5.0","5.5","6.0","6.5","7.0","7.5","8.0","8.5","9.0"].map(x => <option key={x}>{x}</option>)}</select></Field>
      <Field label="Planned test date"><input required type="date" value={date} onChange={(e) => setDate(e.target.value)} style={field} /></Field>
      <div style={{ alignSelf: "end" }}><Button disabled={busy} type="submit">Save goal</Button></div>
    </form></Card><RecordList records={goals} empty="No exam goals yet." /></div>;
}

function PracticeForm({ act, busy, initialSkill }) {
  const [skill, setSkill] = useState(initialSkill), [task, setTask] = useState("original_local_fixture");
  const [prompt, setPrompt] = useState("Summarize the main idea of this original local practice prompt.");
  const [response, setResponse] = useState("");
  useEffect(() => setSkill(initialSkill), [initialSkill]);
  return <Card><Heading level={2}>Structured practice</Heading>
    <Text as="p" tone="muted" size="sm">Use your own or original content. No copyrighted question bank is included.</Text>
    <form onSubmit={(e) => { e.preventDefault(); act(() => ieltsActions.practice({
      skill, task_type: task, prompt, response, duration_seconds: 0,
      idempotency_key: `practice-${skill}-${Date.now()}`,
    }), `${skill} practice submitted; local feedback is ready.`); }} style={{ display: "grid", gap: 12, marginTop: 12 }}>
      <div style={grid}><Field label="Skill"><select value={skill} onChange={(e) => setSkill(e.target.value)} style={field}>
        {["reading","listening","writing","speaking"].map(x => <option key={x}>{x}</option>)}</select></Field>
        <Field label="Task type"><input required maxLength={40} value={task} onChange={(e) => setTask(e.target.value)} style={field} /></Field></div>
      <Field label="Prompt"><textarea required maxLength={4000} rows={3} value={prompt} onChange={(e) => setPrompt(e.target.value)} style={field} /></Field>
      <Field label={skill === "speaking" ? "Transcript (pronunciation will not be assessed)" : "Response / comma-separated answers"}>
        <textarea required maxLength={12000} rows={8} value={response} onChange={(e) => setResponse(e.target.value)} style={field} /></Field>
      <Button disabled={busy} type="submit">Submit practice</Button>
    </form></Card>;
}

function FeedbackView({ records }) {
  const submissions = records.filter((r) => ["practice", "submission"].includes(r.record_type));
  return <><Banner>{IELTS_NOTICE.scoring} Speaking pronunciation is not assessed from transcripts.</Banner>
    <Heading level={2} style={{ marginBottom: 10 }}>Practice history and feedback</Heading>
    <RecordList records={submissions} empty="No practice submissions yet." /></>;
}

function AlertsView({ act, busy, records, token }) {
  const [location, setLocation] = useState("Kathmandu");
  const alerts = records.filter((r) => ["availability_alert", "alert_match"].includes(r.record_type));
  return <div style={{ display: "grid", gap: 14 }}><Banner tone="warn">{IELTS_NOTICE.availability}</Banner>
    <Card><Heading level={2}>Test-center availability alert</Heading><form onSubmit={(e) => {
      e.preventDefault(); act(() => ieltsActions.alert({ exam_type: "academic", test_format: "computer",
        preferred_locations: [location], date_from: "2030-01-01", date_to: "2030-03-31",
        expires_on: "2030-03-31", idempotency_key: `alert-${location}` }), "Alert created.");
    }} style={{ ...grid, marginTop: 12 }}>
      <Field label="Preferred location"><input required maxLength={100} value={location} onChange={(e) => setLocation(e.target.value)} style={field} /></Field>
      <div style={{ alignSelf: "end", display: "flex", gap: 8 }}><Button disabled={busy} type="submit">Create alert</Button>
        <Button disabled={busy} type="button" onClick={() => act(() => ieltsActions.evaluateAlerts(token), "Fixture alerts evaluated.")}>Evaluate fixture</Button></div>
    </form></Card><RecordList records={alerts} empty="No availability alerts yet." /></div>;
}

function PaymentsView({ act, busy, records, token, permissions, userId }) {
  const [reference, setReference] = useState(""), [evidence, setEvidence] = useState("");
  const payments = records.filter((r) => r.record_type === "payment");
  return <div style={{ display: "grid", gap: 14 }}><Banner tone="warn">{IELTS_NOTICE.payment}</Banner>
    <Card><Heading level={2}>Submit manual payment evidence</Heading><form onSubmit={(e) => {
      e.preventDefault(); act(() => ieltsActions.payment({ product: "Local preparation plan", amount: "1500",
        currency: "NPR", payment_method_label: "Bank transfer", transaction_reference: reference,
        evidence_ref: evidence, idempotency_key: `payment-${reference}` }), "Payment evidence submitted for human review.");
    }} style={{ ...grid, marginTop: 12 }}>
      <Field label="Transaction reference"><input required maxLength={120} value={reference} onChange={(e) => setReference(e.target.value)} style={field} /></Field>
      <Field label="Evidence reference"><input required maxLength={500} placeholder="evidence://…" value={evidence} onChange={(e) => setEvidence(e.target.value)} style={field} /></Field>
      <div style={{ alignSelf: "end" }}><Button disabled={busy} type="submit">Submit evidence</Button></div>
    </form></Card>
    <Heading level={2}>Payment records</Heading>
    {!payments.length ? <EmptyState title="No manual payment records." /> : payments.map(p => <Card key={p.record_id}>
      <Text weight={600}>{p.body.product}</Text> <span className="mono">{p.status}</span>
      <Text as="p" tone="muted" size="sm">{p.body.amount} {p.body.currency} · {p.body.disclaimer}</Text>
      {p.status === "submitted" && p.owner_id !== userId && permissions.includes("ielts.payment.review") && <div style={{ display: "flex", gap: 8 }}>
        <Button disabled={busy} onClick={() => act(() => ieltsActions.reviewPayment(p.record_id,
          { approve: true, reason: "Evidence manually compared by authorized reviewer." }, token), "Payment manually approved.")}>Approve as reviewer</Button>
        <Button disabled={busy} onClick={() => act(() => ieltsActions.reviewPayment(p.record_id,
          { approve: false, reason: "Evidence could not be verified." }, token), "Payment rejected.")}>Reject</Button>
      </div>}
      {p.status === "submitted" && (p.owner_id === userId || !permissions.includes("ielts.payment.review")) &&
        <Text as="p" tone="muted" size="sm">Awaiting an authorized human reviewer.</Text>}
    </Card>)}</div>;
}

function EvidenceView({ evidence }) {
  return <><Heading level={2} style={{ marginBottom: 10 }}>IELTS evidence timeline</Heading>
    {!evidence.length ? <EmptyState title="No evidence events yet." /> :
      <ol style={{ display: "grid", gap: 8, paddingLeft: 20 }}>{evidence.map(ev => <li key={ev.event_id}>
        <Card style={{ padding: 12 }}><Text weight={600}>{ev.event_type}</Text>
          <Text as="p" tone="muted" size="sm">{ev.summary}</Text>
          {ev.evidence_ref && <code>{ev.evidence_ref}</code>}</Card></li>)}</ol>}</>;
}

function SettingsView() {
  return <div style={grid}><Card><Heading level={2}>Scoring provider</Heading>
    <Text as="p" tone="muted">Deterministic local heuristic is active. Provider-assisted scoring is not configured.</Text></Card>
    <Card><Heading level={2}>Notifications</Heading><Text as="p" tone="muted">In-app notifications only. No external messages are sent.</Text></Card>
    <Card><Heading level={2}>Availability</Heading><Text as="p" tone="muted">{IELTS_NOTICE.availability}</Text></Card></div>;
}
