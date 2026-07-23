"use client";
/**
 * M50 Platform foundation console — identity, tenancy, approvals, runtime health.
 * Uses /api/v1/platform/* only. No live connectors. Fail-closed.
 */
import { useCallback, useEffect, useState } from "react";
import {
  Card,
  Heading,
  Text,
  Button,
  Input,
  LoadingState,
  ErrorState,
  StatusBadge,
} from "@/components/ui";
import { API_BASE } from "@/lib/api";

const TOKEN_KEY = "saathi_platform_token";

async function plat(path, { method = "GET", body, token } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (token) headers["X-Platform-Token"] = token;
  const res = await fetch(`${API_BASE}/api/v1/platform${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
    credentials: "include",
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = data?.detail?.message || data?.detail?.code || data?.error || res.statusText;
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return data;
}

export default function PlatformPage() {
  const [token, setToken] = useState("");
  const [email, setEmail] = useState("owner@local");
  const [health, setHealth] = useState(null);
  const [me, setMe] = useState(null);
  const [projects, setProjects] = useState([]);
  const [approvals, setApprovals] = useState([]);
  const [config, setConfig] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [echo, setEcho] = useState(null);

  useEffect(() => {
    const t = typeof window !== "undefined" ? localStorage.getItem(TOKEN_KEY) || "" : "";
    setToken(t);
    plat("/health").then(setHealth).catch(() => {});
  }, []);

  const persist = (t) => {
    setToken(t);
    if (typeof window !== "undefined") {
      if (t) localStorage.setItem(TOKEN_KEY, t);
      else localStorage.removeItem(TOKEN_KEY);
    }
  };

  const refresh = useCallback(async (tok) => {
    if (!tok) return;
    setBusy(true);
    setError(null);
    try {
      const [m, p, a, c, h] = await Promise.all([
        plat("/me", { token: tok }),
        plat("/projects", { token: tok }),
        plat("/approvals?status=pending", { token: tok }),
        plat("/config", { token: tok }),
        plat("/health"),
      ]);
      setMe(m);
      setProjects(p.projects || []);
      setApprovals(a.approvals || []);
      setConfig(c.config || null);
      setHealth(h);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    if (token) refresh(token);
  }, [token, refresh]);

  const bootstrap = async () => {
    setBusy(true);
    setError(null);
    try {
      await plat("/bootstrap", {
        method: "POST",
        body: { email, name: "Owner", org_name: "Default Org", workspace_name: "Default Workspace" },
      });
      const login = await plat("/auth/login", { method: "POST", body: { email } });
      persist(login.token);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setBusy(false);
    }
  };

  const login = async () => {
    setBusy(true);
    setError(null);
    try {
      const data = await plat("/auth/login", { method: "POST", body: { email } });
      persist(data.token);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setBusy(false);
    }
  };

  const logout = async () => {
    try {
      await plat("/auth/logout", { method: "POST", token });
    } catch {
      /* ignore */
    }
    persist("");
    setMe(null);
    setProjects([]);
    setApprovals([]);
  };

  const createProject = async () => {
    setBusy(true);
    try {
      await plat("/projects", {
        method: "POST",
        token,
        body: { name: `Project ${new Date().toISOString().slice(0, 16)}` },
      });
      await refresh(token);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setBusy(false);
    }
  };

  const runEcho = async () => {
    setBusy(true);
    setEcho(null);
    try {
      const r = await plat("/execute", {
        method: "POST",
        token,
        body: { tool_id: "m49.echo_readonly", arguments: { text: "m50-platform" } },
      });
      setEcho(r);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page-stack" style={{ maxWidth: 960, margin: "0 auto", padding: "1.5rem" }}>
      <Heading level={1}>Platform foundation</Heading>
      <Text tone="muted">
        M50 identity · RBAC · workspaces · projects · missions · approval center. Executes only
        through the M49 gateway. Connectors remain dry-run. Trading Guardian advisory only.
      </Text>

      {error && <ErrorState title="Platform error" message={error} />}
      {busy && <LoadingState label="Working…" />}

      <Card>
        <Heading level={2}>Runtime health</Heading>
        {health ? (
          <div style={{ display: "grid", gap: 8 }}>
            <StatusBadge status={health.identity === "ACTIVE" ? "ok" : "warn"}>
              Identity {health.identity}
            </StatusBadge>
            <Text>
              RBAC {health.rbac} · Approvals {health.approval_center} · Gateway{" "}
              {health.runtime?.gateway}
            </Text>
            <Text tone="muted">
              {health.runtime?.connectors} · {health.runtime?.trading_guardian}
            </Text>
          </div>
        ) : (
          <Text tone="muted">Health unavailable</Text>
        )}
      </Card>

      <Card>
        <Heading level={2}>Session</Heading>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <Input
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="email"
            aria-label="Email"
          />
          <Button onClick={bootstrap}>Bootstrap + login</Button>
          <Button onClick={login} variant="secondary">
            Login
          </Button>
          {token && (
            <Button onClick={logout} variant="ghost">
              Logout
            </Button>
          )}
        </div>
        {me && (
          <div style={{ marginTop: 12 }}>
            <Text>
              {me.user?.name || me.user?.email} · role {me.context?.role}
            </Text>
            <Text tone="muted">
              org {me.context?.org_id} · workspace {me.context?.workspace_id}
            </Text>
          </div>
        )}
      </Card>

      {token && (
        <>
          <Card>
            <Heading level={2}>Projects</Heading>
            <Button onClick={createProject}>New project</Button>
            <ul style={{ marginTop: 12 }}>
              {projects.map((p) => (
                <li key={p.project_id}>
                  {p.name} <Text tone="muted">({p.project_id})</Text>
                </li>
              ))}
              {!projects.length && <Text tone="muted">No projects yet</Text>}
            </ul>
          </Card>

          <Card>
            <Heading level={2}>Approval inbox (pending)</Heading>
            <ul>
              {approvals.map((a) => (
                <li key={a.approval_id}>
                  {a.tool_id} · {a.status} · {a.approval_id}
                </li>
              ))}
              {!approvals.length && <Text tone="muted">No pending approvals</Text>}
            </ul>
          </Card>

          <Card>
            <Heading level={2}>Runtime execute (read-only demo)</Heading>
            <Button onClick={runEcho}>Echo via ExecutionGateway</Button>
            {echo && (
              <pre style={{ marginTop: 12, fontSize: 12, overflow: "auto" }}>
                {JSON.stringify(echo, null, 2)}
              </pre>
            )}
          </Card>

          <Card>
            <Heading level={2}>Configuration</Heading>
            <pre style={{ fontSize: 12, overflow: "auto" }}>
              {JSON.stringify(config, null, 2)}
            </pre>
          </Card>
        </>
      )}
    </div>
  );
}
