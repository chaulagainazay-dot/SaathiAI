"use client";
/**
 * Stock Price Alerts — per-viewer watch list (localStorage). Set a target and a direction;
 * the alert triggers when the reference LTP crosses it. Observation-only; no orders, no push.
 */
import { useEffect, useState } from "react";
import { getStock } from "@/lib/nepse/data";
import { Button, Badge, Text } from "@/components/ui";

const KEY = "saathi_price_alerts_v1";
const read = () => { try { return JSON.parse(localStorage.getItem(KEY) || "[]"); } catch { return []; } };
const write = (a) => { try { localStorage.setItem(KEY, JSON.stringify(a)); } catch {} };

export default function PriceAlerts() {
  const [alerts, setAlerts] = useState([]);
  const [sym, setSym] = useState("");
  const [target, setTarget] = useState("");
  const [dir, setDir] = useState("above");

  useEffect(() => { setAlerts(read()); }, []);
  const save = (a) => { setAlerts(a); write(a); };

  const add = () => {
    const s = sym.trim().toUpperCase(); const t = parseFloat(target);
    if (!s || !Number.isFinite(t)) return;
    save([...alerts, { id: Date.now(), symbol: s, target: t, dir }]);
    setSym(""); setTarget("");
  };
  const remove = (id) => save(alerts.filter((a) => a.id !== id));

  const inp = { fontFamily: "inherit", fontSize: 12, padding: "7px 10px", borderRadius: 8, background: "#08060a", color: "#f2e8ea", border: "1px solid rgba(255,64,64,.25)", outline: "none" };

  return (
    <div style={{ padding: 14 }}>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: 12 }}>
        <input style={{ ...inp, width: 110 }} placeholder="Symbol" value={sym} onChange={(e) => setSym(e.target.value.toUpperCase())} />
        <select style={inp} value={dir} onChange={(e) => setDir(e.target.value)}>
          <option value="above">crosses above</option>
          <option value="below">crosses below</option>
        </select>
        <input style={{ ...inp, width: 90 }} placeholder="Target" value={target} onChange={(e) => setTarget(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") add(); }} />
        <Button size="sm" onClick={add}>Add alert</Button>
      </div>
      {alerts.length === 0 && <Text tone="muted" size="sm">No alerts yet. Add one above — it triggers when the reference price crosses your target.</Text>}
      {alerts.map((a) => {
        const s = getStock(a.symbol);
        const ltp = s?.ltp ?? null;
        const hit = ltp != null && (a.dir === "above" ? ltp >= a.target : ltp <= a.target);
        return (
          <div key={a.id} style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 0", borderBottom: "1px solid rgba(255,64,64,.07)" }}>
            <span style={{ fontWeight: 700, minWidth: 64 }}>{a.symbol}</span>
            <span style={{ fontSize: 12, color: "#8f8288" }}>{a.dir} {a.target}</span>
            <span style={{ fontSize: 12, color: "#b7a8ad" }}>LTP {ltp ?? "—"}</span>
            <Badge variant="soft" color={hit ? "#2ee27a" : "var(--status-neutral)"} label={hit ? "TRIGGERED" : "watching"} />
            <div style={{ flexGrow: 1 }} />
            <Button size="sm" variant="ghost" onClick={() => remove(a.id)}>✕</Button>
          </div>
        );
      })}
      <Text tone="disabled" size="xs" style={{ display: "block", marginTop: 8 }}>
        Alerts are saved on this device only, checked against the reference LTP · observation-only, no push/orders.
      </Text>
    </div>
  );
}
