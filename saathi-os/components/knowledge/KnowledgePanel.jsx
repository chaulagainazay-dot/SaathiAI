"use client";

import { useCallback, useEffect, useState } from "react";
import { knowledgeActions, safeToken } from "@/lib/knowledge";
import GroundedAnswer from "./GroundedAnswer";

const styles = {
  wrap: {
    display: "flex",
    flexDirection: "column",
    gap: 12,
    padding: 16,
    color: "#e8ecf5",
    maxWidth: 880,
    margin: "0 auto",
  },
  card: {
    border: "1px solid rgba(255,255,255,.1)",
    borderRadius: 14,
    padding: 14,
    background: "rgba(255,255,255,.03)",
  },
  input: {
    width: "100%",
    background: "rgba(255,255,255,.05)",
    color: "#e8ecf5",
    border: "1px solid rgba(255,255,255,.12)",
    borderRadius: 10,
    padding: "10px 12px",
    fontSize: 14,
  },
  btn: {
    background: "rgba(0,191,165,.16)",
    color: "#4fe3cb",
    border: "1px solid rgba(0,191,165,.4)",
    borderRadius: 10,
    padding: "8px 14px",
    cursor: "pointer",
    fontSize: 13,
  },
  btnMuted: {
    background: "rgba(255,255,255,.06)",
    color: "#c5cde0",
    border: "1px solid rgba(255,255,255,.12)",
    borderRadius: 10,
    padding: "8px 14px",
    cursor: "pointer",
    fontSize: 13,
  },
  row: { display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" },
  meta: { fontSize: 12, color: "#9aa8c7", lineHeight: 1.5 },
};

/**
 * Knowledge admin + grounded Q&A surface.
 * Uses ConversationService for answers; knowledge APIs for health/search/reindex only.
 */
export default function KnowledgePanel() {
  const [token, setToken] = useState("");
  const [health, setHealth] = useState(null);
  const [query, setQuery] = useState("What is the current SaathiOS milestone?");
  const [answer, setAnswer] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [canReindex, setCanReindex] = useState(false);

  const refreshHealth = useCallback(async (tok) => {
    if (!tok) return;
    try {
      const data = await knowledgeActions.health(tok);
      setHealth(data.health || data);
      setError("");
    } catch (err) {
      setHealth(null);
      setError(err.message || "Knowledge health unavailable");
    }
  }, []);

  useEffect(() => {
    const t = safeToken();
    setToken(t);
    if (t) refreshHealth(t);
    // Owner/admin typically have reindex; UI probes via attempt failure message.
    setCanReindex(Boolean(t));
    return () => {
      setAnswer(null);
      setHealth(null);
      setToken("");
    };
  }, [refreshHealth]);

  // Workspace switch / logout invalidation when token changes via storage
  useEffect(() => {
    function onStorage(e) {
      if (!e || e.key === "saathi_platform_token" || e.key === "token") {
        const t = safeToken();
        setToken(t);
        setAnswer(null);
        if (t) refreshHealth(t);
        else {
          setHealth(null);
        }
      }
    }
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, [refreshHealth]);

  async function ask(e) {
    e?.preventDefault?.();
    if (!token || !query.trim()) return;
    setBusy(true);
    setError("");
    try {
      const data = await knowledgeActions.completeGrounded(token, query.trim());
      setAnswer(data.result || data);
    } catch (err) {
      setError(err.message || "Grounded ask failed");
      setAnswer(null);
    } finally {
      setBusy(false);
    }
  }

  async function reindex() {
    if (!token || !canReindex) return;
    setBusy(true);
    setError("");
    try {
      await knowledgeActions.reindex(token, false);
      await refreshHealth(token);
    } catch (err) {
      setError(err.message || "Reindex denied or failed");
      if (String(err.message || "").toLowerCase().includes("permission")) {
        setCanReindex(false);
      }
    } finally {
      setBusy(false);
    }
  }

  if (!token) {
    return (
      <div style={styles.wrap} data-knowledge-panel="signed-out">
        <p role="status">Sign in to use the Knowledge and Grounding Runtime.</p>
      </div>
    );
  }

  return (
    <div style={styles.wrap} data-knowledge-panel="active" aria-label="Knowledge grounding">
      <header>
        <h1 style={{ fontSize: 22, margin: "0 0 6px" }}>Knowledge & Grounding</h1>
        <p style={styles.meta}>
          Answers come through ConversationService with lexical retrieval over approved
          local sources. Production is not authorized from this surface.
        </p>
      </header>

      <section style={styles.card} aria-label="Knowledge health">
        <div style={styles.row}>
          <strong>Health</strong>
          <span className="knowledge-badge" data-ready={health?.ready ? "true" : "false"}>
            {health?.ready ? "Ready" : "Not ready"}
          </span>
          <button type="button" style={styles.btnMuted} onClick={() => refreshHealth(token)} disabled={busy}>
            Refresh
          </button>
          <button
            type="button"
            style={styles.btnMuted}
            onClick={reindex}
            disabled={busy || !canReindex}
            aria-label="Reindex knowledge sources"
          >
            Reindex
          </button>
        </div>
        {health ? (
          <div style={{ ...styles.meta, marginTop: 8 }} data-testid="knowledge-health">
            <div>Sources indexed: {health.sources_indexed} / discovered {health.sources_discovered}</div>
            <div>Chunks: {health.chunks_indexed}</div>
            <div>Mode: {health.retrieval_mode} (semantic: {String(health.semantic_available)})</div>
            <div>Repo SHA: {health.repository_sha || "—"}</div>
            <div>Index: {health.index_version}</div>
          </div>
        ) : null}
      </section>

      <section style={styles.card} aria-label="Grounded question">
        <form onSubmit={ask}>
          <label htmlFor="knowledge-query" style={{ display: "block", marginBottom: 8, fontSize: 13 }}>
            Ask Yeti (grounded)
          </label>
          <textarea
            id="knowledge-query"
            style={{ ...styles.input, minHeight: 72, resize: "vertical" }}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            maxLength={500}
            aria-label="Grounded question"
          />
          <div style={{ ...styles.row, marginTop: 10 }}>
            <button type="submit" style={styles.btn} disabled={busy}>
              {busy ? "Working…" : "Ask"}
            </button>
          </div>
        </form>
        {error ? (
          <p role="alert" style={{ color: "#ff8c8c", marginTop: 10 }}>
            {error}
          </p>
        ) : null}
        {answer ? (
          <div style={{ marginTop: 14 }}>
            <GroundedAnswer text={answer.text || ""} grounding={answer.grounding || {}} />
          </div>
        ) : null}
      </section>
    </div>
  );
}
