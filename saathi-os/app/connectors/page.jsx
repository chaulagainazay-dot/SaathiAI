"use client";
import { useEffect, useState } from "react";
import { Panel, Eyebrow } from "@/components/ui";
import { fetchConnectorProviders, fetchAccounts, addAccount, linkAccountMission, fetchMissions } from "@/lib/api";

const ACCENT = "#7CF5E4", TEAL = "#00BFA5", AMBER = "#E8B84B", RED = "#FF5A5A";

export default function Connectors() {
  const [providers, setProviders] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [health, setHealth] = useState({});
  const [missions, setMissions] = useState([]);
  const [form, setForm] = useState({ provider: "gmail", display_name: "", email: "" });
  const [err, setErr] = useState(null);
  const load = () => {
    fetchAccounts().then((d) => { setAccounts(d.accounts || []); setHealth(d.health || {}); }).catch((e) => setErr(String(e)));
  };
  useEffect(() => {
    fetchConnectorProviders().then((d) => setProviders(d.providers || [])).catch((e) => setErr(String(e)));
    fetchMissions().then((d) => setMissions(d.missions || [])).catch(() => {});
    load();
  }, []);

  const add = async () => {
    try { await addAccount(form); setForm({ ...form, display_name: "", email: "" }); load(); }
    catch (e) { setErr(`${e} — login may be required`); }
  };
  const toggle = async (aid, key, on) => { try { await linkAccountMission(aid, key, on); load(); } catch (e) { setErr(String(e)); } };

  const byCat = {};
  providers.forEach((p) => { (byCat[p.category] = byCat[p.category] || []).push(p); });
  const statusColor = (s) => (s === "connected" ? TEAL : s === "expired" ? RED : AMBER);

  return (
    <div className="page" style={{ maxWidth: 1000, margin: "0 auto", paddingBottom: 60 }}>
      <Eyebrow style={{ color: ACCENT }}>SaathiOS · Connectors</Eyebrow>
      <div style={{ fontSize: 28, fontWeight: 600, margin: "4px 0 4px" }}>Accounts & Connectors</div>
      <div style={{ fontSize: 13, opacity: 0.5, marginBottom: 16 }}>
        One layer every Mission & Director uses to reach external services. Secrets encrypted, never in Git; every action → Evidence.
      </div>

      {/* health strip */}
      <div style={{ display: "flex", gap: 12, marginBottom: 16, flexWrap: "wrap" }}>
        {[["Accounts", health.total || 0], ["Connected", health.connected || 0],
          ["Expired", health.expired || 0], ["Providers", providers.length]].map(([k, v]) => (
          <div key={k} className="glass" style={{ padding: "10px 18px", borderRadius: 12, minWidth: 110 }}>
            <div style={{ fontSize: 22, fontWeight: 600, color: ACCENT }}>{v}</div>
            <div style={{ fontSize: 11, opacity: 0.55 }}>{k}</div>
          </div>
        ))}
      </div>
      {err && <div style={{ fontSize: 12, color: RED, marginBottom: 10 }}>{err}</div>}

      {/* add account */}
      <Panel style={{ padding: 16, marginBottom: 16 }}>
        <Eyebrow style={{ color: ACCENT }}>Connect an account</Eyebrow>
        <div style={{ display: "flex", gap: 8, marginTop: 10, flexWrap: "wrap" }}>
          <select value={form.provider} onChange={(e) => setForm({ ...form, provider: e.target.value })}
            style={inp(160)}>
            {providers.map((p) => <option key={p.provider} value={p.provider} style={{ color: "#000" }}>{p.provider}</option>)}
          </select>
          <input placeholder="Display name" value={form.display_name}
            onChange={(e) => setForm({ ...form, display_name: e.target.value })} style={inp(180)} />
          <input placeholder="Email / handle" value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })} style={inp(180)} />
          <button onClick={add} style={{ padding: "0 18px", borderRadius: 9, border: "none", cursor: "pointer",
            fontWeight: 600, color: "#000", background: ACCENT }}>＋ Add</button>
        </div>
        <div style={{ fontSize: 10.5, opacity: 0.4, marginTop: 6 }}>
          Live OAuth is added adapter-by-adapter; accounts registered now run through the layer in simulated mode.
        </div>
      </Panel>

      {/* connected accounts */}
      <Panel style={{ padding: 16, marginBottom: 16 }}>
        <Eyebrow style={{ color: ACCENT }}>Connected accounts</Eyebrow>
        <div style={{ marginTop: 10 }}>
          {accounts.length === 0 && <div style={{ fontSize: 12.5, opacity: 0.4 }}>none yet</div>}
          {accounts.map((a) => (
            <div key={a.id} style={{ padding: "10px 0", borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ width: 8, height: 8, borderRadius: "50%", background: statusColor(a.status) }} />
                <b style={{ fontSize: 13.5 }}>{a.display_name}</b>
                <span className="mono" style={{ fontSize: 11, opacity: 0.5 }}>{a.provider}{a.email ? ` · ${a.email}` : ""}</span>
                <span className="mono" style={{ marginLeft: "auto", fontSize: 10.5, color: statusColor(a.status) }}>{a.status}</span>
              </div>
              <div style={{ display: "flex", gap: 6, marginTop: 6, flexWrap: "wrap" }}>
                {missions.map((m) => {
                  const on = (a.missions || []).includes(m.key);
                  return (
                    <button key={m.key} onClick={() => toggle(a.id, m.key, !on)}
                      style={{ fontSize: 10.5, padding: "3px 10px", borderRadius: 999, cursor: "pointer",
                        border: `1px solid ${on ? TEAL : "rgba(255,255,255,0.15)"}`,
                        background: on ? `${TEAL}22` : "transparent", color: on ? TEAL : "inherit" }}>
                      {on ? "✓ " : ""}{m.name}</button>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </Panel>

      {/* provider catalog */}
      <Panel style={{ padding: 16 }}>
        <Eyebrow style={{ color: ACCENT }}>Provider catalog · {providers.length}</Eyebrow>
        {Object.entries(byCat).map(([cat, ps]) => (
          <div key={cat} style={{ marginTop: 10 }}>
            <div style={{ fontSize: 11, opacity: 0.5, textTransform: "capitalize" }}>{cat}</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 4 }}>
              {ps.map((p) => (
                <span key={p.provider} className="mono" title={`${p.auth_type} · ${p.capabilities.join(", ")}`}
                  style={{ fontSize: 10.5, padding: "3px 9px", borderRadius: 999, background: "rgba(255,255,255,0.05)" }}>
                  {p.provider}</span>
              ))}
            </div>
          </div>
        ))}
      </Panel>
    </div>
  );
}

const inp = (w) => ({ width: w, padding: "8px 11px", borderRadius: 9, fontSize: 13,
  border: "1px solid rgba(255,255,255,0.12)", background: "rgba(255,255,255,0.04)", color: "inherit" });
