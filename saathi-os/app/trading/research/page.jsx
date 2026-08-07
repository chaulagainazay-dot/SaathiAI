"use client";
// M178–M183 — Walk-forward + stress research lab (paper only)
import { Card, Heading, Text, Button } from "@/components/ui";
import { TradingTabs, TradingHeader, SafetyBanner, SignInGate, LoadError }
  from "@/components/trading/TradingShell";
import { useAuthMe } from "@/lib/trading";
import { plat } from "@/lib/platform-client";
import { useState } from "react";

export default function TradingResearchPage() {
  const d = useAuthMe();
  const [wf, setWf] = useState(null);
  const [stress, setStress] = useState(null);
  const [score, setScore] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [slug, setSlug] = useState("trend_following");

  const run = async (kind) => {
    if (!d.token || busy) return;
    setBusy(true); setError(null);
    try {
      if (kind === "wf") {
        setWf(await plat("/tg/walk-forward", {
          method: "POST", token: d.token,
          body: { strategy_slug: slug, dataset: "TRENDING", n: 50, n_folds: 3 },
        }));
      } else if (kind === "stress") {
        setStress(await plat("/tg/stress", {
          method: "POST", token: d.token,
          body: { strategy_slug: slug, dataset: "TRENDING", n: 40 },
        }));
      } else {
        setScore(await plat(`/tg/scorecard/${slug}`, { token: d.token }));
      }
    } catch (e) {
      setError(e?.message || String(e));
    } finally { setBusy(false); }
  };

  return (
    <div className="page shell-page">
      <TradingHeader title="Research Lab"
        subtitle="Walk-forward and stress testing. Synthetic/fixture datasets are labeled and never treated as live market evidence." />
      <TradingTabs />
      <SignInGate ready={d.ready} token={d.token}>
        <SafetyBanner />
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
          <span className="mono" data-testid="paper-only" style={pill("#10C98A")}>PAPER TRADING ONLY</span>
          <span className="mono" style={pill("#5B8CFF")}>NO LIVE ORDERS</span>
          <span className="mono" style={pill("#8FA0C4")}>SIMULATED FUNDS</span>
          <span className="mono" style={pill("#F5A623")}>NO PROFITABILITY CLAIM</span>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
          {["trend_following", "kotegawa_mean_reversion", "momentum_rs", "no_trade"].map((s) => (
            <Button key={s} onClick={() => setSlug(s)} data-testid={`select-${s}`}>
              {s === slug ? `● ${s}` : s}
            </Button>
          ))}
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <Button onClick={() => run("wf")} disabled={busy} data-testid="run-walk-forward">Walk-forward</Button>
          <Button onClick={() => run("stress")} disabled={busy} data-testid="run-stress">Stress lab</Button>
          <Button onClick={() => run("score")} disabled={busy} data-testid="run-scorecard">Scorecard</Button>
        </div>
        {error ? <LoadError error={error} /> : null}
        {wf ? (
          <Card style={{ marginTop: 16 }} data-testid="walk-forward-result">
            <Heading level={2} size="md">Walk-forward · consistent={String(wf.walk_forward_consistent)}</Heading>
            <Text mono size="sm">
              folds {wf.n_folds} · OOS expectancy {wf.out_of_sample_expectancy} ·
              worst DD {wf.worst_fold_drawdown} · param stability {wf.parameter_stability} ·
              final test untouched={String(wf.final_test_untouched)} · {wf.data_classification}
            </Text>
          </Card>
        ) : null}
        {stress ? (
          <Card style={{ marginTop: 16 }} data-testid="stress-result">
            <Heading level={2} size="md">Stress · {stress.robustness_verdict}</Heading>
            <Text mono size="sm">
              critical failures {stress.critical_failures} · promote_blocked={String(stress.promote_blocked)} ·
              cases {(stress.cases || []).length} · {stress.data_classification}
            </Text>
          </Card>
        ) : null}
        {score ? (
          <Card style={{ marginTop: 16 }} data-testid="scorecard-result">
            <Heading level={2} size="md">Scorecard · {score.scorecard?.verdict}</Heading>
            <pre className="mono" style={{ fontSize: 11, overflow: "auto", maxHeight: 320 }}>
              {JSON.stringify(score.scorecard?.eligibility_checklist || score.scorecard, null, 2)}
            </pre>
          </Card>
        ) : null}
      </SignInGate>
    </div>
  );
}

function pill(c) {
  return { fontSize: 11, border: `1px solid ${c}`, color: c, borderRadius: 6, padding: "2px 8px" };
}
