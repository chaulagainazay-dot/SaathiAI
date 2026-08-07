"use client";
// M184–M191 — Historical market data workspace (paper research only)
import { Card, Heading, Text, Button } from "@/components/ui";
import { TradingTabs, TradingHeader, SafetyBanner, SignInGate, LoadError }
  from "@/components/trading/TradingShell";
import { useAuthMe } from "@/lib/trading";
import { plat } from "@/lib/platform-client";
import { useState } from "react";

export default function TradingHistoricalPage() {
  const d = useAuthMe();
  const [datasets, setDatasets] = useState(null);
  const [calendars, setCalendars] = useState(null);
  const [quarantine, setQuarantine] = useState(null);
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = async (kind) => {
    if (!d.token || busy) return;
    setBusy(true); setError(null);
    try {
      if (kind === "list") {
        setDatasets(await plat("/tg/historical/datasets", { token: d.token }));
      } else if (kind === "calendars") {
        setCalendars(await plat("/tg/historical/calendars", { token: d.token }));
      } else if (kind === "quarantine") {
        setQuarantine(await plat("/tg/historical/quarantine", { token: d.token }));
      }
    } catch (e) {
      setError(e?.message || String(e));
    } finally { setBusy(false); }
  };

  const inspect = async (id) => {
    if (!d.token || busy) return;
    setBusy(true); setError(null);
    try {
      setDetail(await plat(`/tg/historical/datasets/${id}`, { token: d.token }));
    } catch (e) {
      setError(e?.message || String(e));
    } finally { setBusy(false); }
  };

  return (
    <div className="page shell-page">
      <TradingHeader title="Historical Data"
        subtitle="Operator-supplied local historical datasets. Read-only adapters. No live broker. No live orders." />
      <TradingTabs />
      <SignInGate ready={d.ready} token={d.token}>
        <SafetyBanner />
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
          <span className="mono" data-testid="paper-research-only" style={pill("#10C98A")}>PAPER RESEARCH ONLY</span>
          <span className="mono" data-testid="no-live-orders" style={pill("#5B8CFF")}>NO LIVE ORDERS</span>
          <span className="mono" style={pill("#F5A623")}>HISTORICAL RESULTS ARE NOT FUTURE RESULTS</span>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <Button onClick={() => load("list")} disabled={busy} data-testid="list-datasets">List datasets</Button>
          <Button onClick={() => load("calendars")} disabled={busy} data-testid="list-calendars">Calendars</Button>
          <Button onClick={() => load("quarantine")} disabled={busy} data-testid="list-quarantine">Quarantine</Button>
        </div>
        {error ? <LoadError error={error} /> : null}
        {datasets ? (
          <Card style={{ marginTop: 16 }} data-testid="datasets-result">
            <Heading level={2} size="md">Datasets · {datasets.datasets?.length || 0}</Heading>
            <Text mono size="sm">store versions {datasets.store?.versions} · quarantine {datasets.store?.quarantine}</Text>
            <ul style={{ marginTop: 8 }}>
              {(datasets.datasets || []).map((ds) => (
                <li key={ds.id}>
                  <button type="button" className="mono" data-testid={`dataset-${ds.id}`}
                    onClick={() => inspect(ds.id)}
                    style={{ background: "none", border: "none", color: "#5B8CFF", cursor: "pointer" }}>
                    {ds.name || ds.id} · {ds.market || "—"} · v{ds.latest_version || "—"}
                  </button>
                </li>
              ))}
            </ul>
            {(datasets.datasets || []).length === 0 ? (
              <Text size="sm" tone="muted">
                No datasets imported yet. Use CLI `python -m saathi.platform.tg data import &lt;csv&gt;` or POST /tg/historical/import with a local path.
              </Text>
            ) : null}
          </Card>
        ) : null}
        {detail ? (
          <Card style={{ marginTop: 16 }} data-testid="dataset-detail">
            <Heading level={2} size="md">
              Detail · {detail.version?.classification} · {detail.version?.quality?.verdict}
            </Heading>
            <Text mono size="sm">
              fingerprint {detail.version?.fingerprint?.content_fingerprint?.slice(0, 16)}… ·
              rows {detail.version?.row_count} · promotable={String(detail.promotable)} ·
              immutable={String(detail.version?.immutable)} · {detail.version?.adapter}
            </Text>
            <pre className="mono" style={{ fontSize: 11, overflow: "auto", maxHeight: 240 }}>
              {JSON.stringify({
                coverage: detail.version?.coverage,
                quality: detail.version?.quality,
                corporate_action_status: detail.version?.corporate_action_status,
              }, null, 2)}
            </pre>
          </Card>
        ) : null}
        {calendars ? (
          <Card style={{ marginTop: 16 }} data-testid="calendars-result">
            <Heading level={2} size="md">Market calendars</Heading>
            <Text mono size="sm">{(calendars.supported || []).join(", ")}</Text>
          </Card>
        ) : null}
        {quarantine ? (
          <Card style={{ marginTop: 16 }} data-testid="quarantine-result">
            <Heading level={2} size="md">Quarantine · {(quarantine.quarantine || []).length}</Heading>
            <Text size="sm">Quarantined datasets cannot promote strategies.</Text>
          </Card>
        ) : null}
      </SignInGate>
    </div>
  );
}

function pill(c) {
  return { fontSize: 11, border: `1px solid ${c}`, color: c, borderRadius: 6, padding: "2px 8px" };
}
