"use client";
import { useEffect, useState } from "react";
import { Panel, Eyebrow } from "@/components/ui";
import { fetchLabPrompts, fetchLabPrompt, rollbackLabPrompt } from "@/lib/api";

const CYAN = "#22D3EE";
const pct = (s) => (s == null ? "—" : `${Math.round(s * 100)}%`);

export default function AILab() {
  const [cat, setCat] = useState([]);
  const [open, setOpen] = useState(null);   // { name, versions, leaderboard }
  const load = () => fetchLabPrompts().then((d) => setCat(d.prompts || [])).catch(() => {});
  useEffect(() => { load(); }, []);

  const openPrompt = (name) => fetchLabPrompt(name).then(setOpen).catch(() => {});
  const doRollback = (name, v) =>
    rollbackLabPrompt(name, v).then(() => { openPrompt(name); load(); }).catch(() => {});

  return (
    <div className="only-desktop" style={{ maxWidth: 1000, margin: "0 auto" }}>
      <Eyebrow style={{ color: CYAN }}>AI Lab</Eyebrow>
      <div style={{ fontSize: 26, fontWeight: 600, margin: "4px 0 6px" }}>Prompt Library</div>
      <div style={{ fontSize: 13, opacity: 0.5, marginBottom: 20 }}>
        Every prompt is versioned, measurable, and rollback-able — one shared service for
        HCG · PIELTS · Mr. Yeti · Saathi. The foundation of Production Intelligence.
      </div>

      <div style={{ display: "grid", gridTemplateColumns: open ? "1fr 1fr" : "1fr", gap: 16 }}>
        <Panel style={{ padding: 0, overflow: "hidden" }}>
          {cat.length === 0
            ? <div style={{ padding: 18, opacity: 0.4, fontSize: 13 }}>no prompts yet</div>
            : cat.map((p) => (
              <div key={p.name} onClick={() => openPrompt(p.name)}
                style={{ padding: "12px 16px", borderBottom: "1px solid rgba(255,255,255,0.05)",
                  cursor: "pointer", display: "flex", justifyContent: "space-between",
                  background: open?.name === p.name ? "rgba(34,211,238,0.08)" : "transparent" }}>
                <div>
                  <div style={{ fontSize: 14 }}>{p.name}</div>
                  <div style={{ fontSize: 11, opacity: 0.45 }}>{p.project} · v{p.active_version} · {p.versions} versions</div>
                </div>
                <div style={{ textAlign: "right", fontSize: 13 }}>
                  <div style={{ color: CYAN }}>{pct(p.active_score)}</div>
                  <div style={{ fontSize: 10, opacity: 0.4 }}>best {pct(p.best_score)}</div>
                </div>
              </div>
            ))}
        </Panel>

        {open && (
          <Panel style={{ padding: 18 }}>
            <Eyebrow style={{ color: CYAN }}>{open.name}</Eyebrow>
            <div style={{ fontSize: 11, opacity: 0.45, margin: "6px 0 12px" }}>version history · leaderboard</div>
            {(open.leaderboard || []).map((v) => (
              <div key={v.version} style={{ padding: "8px 0", borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
                  <span>v{v.version} {v.active ? <b style={{ color: CYAN }}>● active</b> : ""}</span>
                  <span style={{ opacity: 0.7 }}>
                    {pct(v.score)} {v.latency_ms ? `· ${(v.latency_ms/1000).toFixed(1)}s` : ""} {v.failures != null ? `· ${v.failures} fail` : ""}
                  </span>
                </div>
                <div style={{ fontSize: 11, opacity: 0.4, marginTop: 2 }}>
                  {v.author} · {v.notes || v.purpose}
                  {!v.active && <button onClick={() => doRollback(open.name, v.version)}
                    style={{ marginLeft: 10, background: "none", border: "1px solid rgba(34,211,238,0.4)",
                      color: CYAN, borderRadius: 8, fontSize: 10, padding: "1px 8px", cursor: "pointer" }}>
                    redeploy</button>}
                </div>
              </div>
            ))}
          </Panel>
        )}
      </div>
    </div>
  );
}
