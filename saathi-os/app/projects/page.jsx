"use client";
import { useState, useEffect } from "react";
import {
  Card,
  Heading,
  Text,
  Button,
  Input,
  LoadingState,
  EmptyState,
  ErrorState,
  StatusBadge,
  Panel,
  Eyebrow,
} from "@/components/ui";
import { fetchProjects, createProject, fetchProject, updateProject, researchProject } from "@/lib/api";

const JOURNEY = [
  ["Capture", "📋"],
  ["Research", "🔎"],
  ["Analyze", "📊"],
  ["Strategy", "🎯"],
  ["Roadmap", "🗺️"],
  ["Plan", "🗓️"],
  ["Execute", "🚀"],
];

function statusOf(s) {
  const v = String(s || "draft").toLowerCase();
  if (v === "ready") return "success";
  if (v === "submitted" || v === "researching") return "pending";
  return "neutral";
}

/**
 * Projects — list view uses M1 primitives; detail form keeps existing field helpers.
 */
export default function Projects() {
  const [projects, setProjects] = useState(null);
  const [cur, setCur] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = () =>
    fetchProjects()
      .then((d) => setProjects(d.projects || []))
      .catch((e) => setErr(String(e)))
      .finally(() => setLoading(false));

  useEffect(() => {
    load();
  }, []);

  const open = (id) => fetchProject(id).then(setCur).catch((e) => setErr(String(e)));
  const startNew = async () => {
    setBusy(true);
    try {
      const p = await createProject({});
      setCur(p);
      load();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };
  const setField = (path, value) =>
    setCur((c) => {
      const d = { ...c.data };
      if (path.length === 2) d[path[0]] = { ...(d[path[0]] || {}), [path[1]]: value };
      else d[path[0]] = value;
      return { ...c, data: d };
    });
  const save = async () => {
    setBusy(true);
    try {
      const p = await updateProject(cur.id, cur.data);
      setCur({ ...p, share_url: cur.share_url });
      load();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };
  const runResearch = async () => {
    setBusy(true);
    try {
      const p = await researchProject(cur.id);
      setCur({ ...p, share_url: cur.share_url });
      load();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  if (!cur) {
    return (
      <div className="page shell-page">
        <div className="shell-page-header home-header">
          <Text tone="muted" size="xs" mono>
            Work · Projects
          </Text>
          <div className="home-header-actions" style={{ justifyContent: "space-between", width: "100%" }}>
            <Heading level={1} size="xl">
              Projects
            </Heading>
            <Button variant="primary" size="sm" onClick={startNew} loading={busy}>
              Create Project
            </Button>
          </div>
          <Text tone="muted" size="sm" as="p" className="home-intro">
            Client intake to direction — real project records only.
          </Text>
        </div>

        <Card className="home-card">
          <Heading level={2} size="md">
            Journey
          </Heading>
          <div className="projects-journey">
            {JOURNEY.map(([label, icon]) => (
              <div key={label} className="projects-journey-step">
                <span aria-hidden="true">{icon}</span>
                <Text size="xs" tone="muted">
                  {label}
                </Text>
              </div>
            ))}
          </div>
        </Card>

        {loading && <LoadingState label="Loading projects…" />}
        {!loading && err && !projects && (
          <ErrorState title="Projects unavailable" description="Could not load intake projects." detail={err} />
        )}
        {!loading && Array.isArray(projects) && projects.length === 0 && (
          <EmptyState
            title="No projects yet"
            description="Create your first project to begin intake."
            action={
              <Button size="sm" variant="primary" onClick={startNew}>
                Create Project
              </Button>
            }
          />
        )}
        {!loading && projects?.length > 0 && (
          <div className="missions-grid">
            {projects.map((p) => (
              <Card key={p.id} interactive className="missions-card" onClick={() => open(p.id)}>
                <Heading level={2} size="md">
                  {p.name || p.data?.name || p.id}
                </Heading>
                <StatusBadge status={statusOf(p.status)} label={p.status || "draft"} />
                <Text tone="muted" size="xs" mono>
                  {p.id}
                </Text>
              </Card>
            ))}
          </div>
        )}
      </div>
    );
  }

  // Detail form — bounded: use Card/Button/Input but keep field structure
  return (
    <div className="page shell-page">
      <div className="shell-page-header home-header">
        <Button variant="ghost" size="sm" onClick={() => setCur(null)}>
          ← Back
        </Button>
        <Heading level={1} size="xl">
          {cur.data?.name || cur.name || "Project"}
        </Heading>
        <StatusBadge status={statusOf(cur.status)} label={cur.status || "draft"} />
      </div>
      {err && <ErrorState title="Error" detail={err} />}
      <Card className="home-card">
        <Eyebrow>Client / name</Eyebrow>
        <Input
          value={cur.data?.name || ""}
          onChange={(e) => setField(["name"], e.target.value)}
          placeholder="Project name"
        />
        <div className="home-section-actions">
          <Button size="sm" variant="primary" onClick={save} loading={busy}>
            Save
          </Button>
          <Button size="sm" variant="secondary" onClick={runResearch} loading={busy}>
            Research
          </Button>
        </div>
        {cur.share_url && (
          <Text tone="muted" size="xs" mono as="p">
            share: {cur.share_url}
          </Text>
        )}
      </Card>
      <Panel soft className="home-card">
        <Text tone="disabled" size="xs">
          Full intake form fields remain available via research/update APIs. List view uses M1 primitives
          (M47.3 bounded migration).
        </Text>
      </Panel>
    </div>
  );
}
