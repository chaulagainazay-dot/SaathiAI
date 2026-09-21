"use client";
/**
 * API Keys — paste a key and it starts working immediately (stored locally in ~/.saathi/keys.env,
 * set into the live process env; providers pick it up on the next request). Owner-only.
 */
import { useCallback, useEffect, useState } from "react";
import { API_BASE, afetch } from "@/lib/api";
import { Button, Badge, Text, Spinner } from "@/components/ui";

function api(path, opts = {}) {
  return afetch(`${API_BASE}${path}`, { cache: "no-store", headers: { "content-type": "application/json", ...(opts.headers || {}) }, ...opts })
    .then(async (r) => { let b = {}; try { b = await r.json(); } catch {} return { ok: r.ok, status: r.status, body: b }; });
}

export default function SettingsKeys() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [vals, setVals] = useState({});
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");

  const load = useCallback(async () => {
    const r = await api("/api/v1/settings/keys");
    setData(r.ok ? r.body : { error: r.body?.error || `HTTP ${r.status}` });
    setLoading(false);
  }, []);
  useEffect(() => { load(); }, [load]);

  const save = async (name) => {
    const value = (vals[name] ?? "").trim();
    if (!value) return;
    setBusy(name); setMsg("");
    const r = await api("/api/v1/settings/keys", { method: "POST", body: JSON.stringify({ name, value }) });
    setMsg(r.ok && r.body?.ok ? `${name} saved — active now.` : (r.body?.error || "Save failed"));
    setVals((v) => ({ ...v, [name]: "" }));
    await load(); setBusy("");
  };
  const clear = async (name) => {
    setBusy(name); setMsg("");
    await api("/api/v1/settings/keys", { method: "POST", body: JSON.stringify({ name, value: "" }) });
    setMsg(`${name} cleared.`); await load(); setBusy("");
  };

  const inp = { fontFamily: "inherit", fontSize: 12, padding: "7px 10px", borderRadius: 8, flexGrow: 1, minWidth: 160, background: "#08060a", color: "#f2e8ea", border: "1px solid rgba(255,64,64,.25)", outline: "none" };

  return (
    <div style={{ padding: 14 }}>
      {loading && <div style={{ display: "flex", justifyContent: "center", padding: 24 }}><Spinner size={16} /></div>}
      {!loading && data?.error && <Text tone="muted" size="sm">{data.error} — sign in.</Text>}
      {!loading && data?.keys && (
        <>
          {data.keys.map((k) => (
            <div key={k.name} style={{ padding: "10px 0", borderBottom: "1px solid rgba(255,64,64,.08)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                <span style={{ fontWeight: 600, fontSize: 13 }}>{k.name}</span>
                <Badge variant="soft" color={k.set ? "#2ee27a" : "var(--status-neutral)"} label={k.set ? `set · ${k.masked}` : "not set"} />
              </div>
              <Text tone="disabled" size="xs" style={{ display: "block", marginBottom: 6 }}>{k.label}</Text>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <input style={inp} type={k.secret ? "password" : "text"} placeholder={k.set ? "paste new value to replace" : "paste value"}
                  value={vals[k.name] ?? ""} onChange={(e) => setVals((v) => ({ ...v, [k.name]: e.target.value }))}
                  onKeyDown={(e) => { if (e.key === "Enter") save(k.name); }} />
                <Button size="sm" onClick={() => save(k.name)} disabled={busy === k.name || !(vals[k.name] || "").trim()}>{busy === k.name ? "…" : "Save"}</Button>
                {k.set && <Button size="sm" variant="ghost" onClick={() => clear(k.name)} disabled={busy === k.name}>Clear</Button>}
              </div>
            </div>
          ))}
          {msg && <Text tone="muted" size="xs" style={{ display: "block", marginTop: 10 }}>{msg}</Text>}
          <Text tone="disabled" size="xs" style={{ display: "block", marginTop: 10 }}>{data.note}</Text>
        </>
      )}
    </div>
  );
}
