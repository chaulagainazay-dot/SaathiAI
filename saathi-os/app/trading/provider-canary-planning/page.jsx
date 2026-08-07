"use client";
import { Card, Heading, Text, Button } from "@/components/ui";
import { TradingTabs, TradingHeader, SafetyBanner, SignInGate, LoadError }
  from "@/components/trading/TradingShell";
import { useAuthMe } from "@/lib/trading";
import { plat } from "@/lib/platform-client";
import { useState } from "react";

/** M247 — Provider Canary Planning Control Center.
 *  PLANNING ONLY.
 *  NO REAL CONNECTIVITY. NO CREDENTIALS. NO ACCOUNT ACCESS.
 *  CANARY NOT AUTHORIZED. LIVE TRADING NOT AUTHORIZED.
 */
export default function ProviderCanaryPlanningPage() {
  const d = useAuthMe();
  const [dash, setDash] = useState(null);
  const [verdict, setVerdict] = useState(null);
  const [rank, setRank] = useState(null);
  const [preferred, setPreferred] = useState(null);
  const [fallback, setFallback] = useState(null);
  const [sources, setSources] = useState(null);
  const [caps, setCaps] = useState(null);
  const [scopes, setScopes] = useState(null);
  const [elig, setElig] = useState(null);
  const [terms, setTerms] = useState(null);
  const [canary, setCanary] = useState(null);
  const [cred, setCred] = useState(null);
  const [accept, setAccept] = useState(null);
  const [abort, setAbort] = useState(null);
  const [owner, setOwner] = useState(null);
  const [net, setNet] = useState(null);
  const [sec, setSec] = useState(null);
  const [ownerBlock, setOwnerBlock] = useState(null);
  const [activateBlock, setActivateBlock] = useState(null);
  const [credBlock, setCredBlock] = useState(null);
  const [error, setError] = useState(null);

  const load = async (path, setter, method = "GET", body = undefined) => {
    if (!d.token) return;
    setError(null);
    try {
      const opts = { token: d.token, method };
      if (body !== undefined) opts.body = body;
      setter(await plat(path, opts));
    } catch (e) {
      setError(e?.message || String(e));
    }
  };

  return (
    <div className="page shell-page">
      <TradingHeader
        title="Provider Canary Planning Control Center"
        subtitle="Provider selection, read-only canary design and human authorization package only."
      />
      <TradingTabs />
      <SignInGate ready={d.ready} token={d.token}>
        <SafetyBanner />
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
          <span className="mono" data-testid="planning-only" style={pill("#5B8CFF")}>PLANNING ONLY</span>
          <span className="mono" data-testid="no-real-connectivity" style={pill("#FF5A5A")}>NO REAL CONNECTIVITY</span>
          <span className="mono" data-testid="no-credentials" style={pill("#F5A623")}>NO CREDENTIALS</span>
          <span className="mono" data-testid="no-account-access" style={pill("#F5A623")}>NO ACCOUNT ACCESS</span>
          <span className="mono" data-testid="canary-not-authorized" style={pill("#FF5A5A")}>CANARY NOT AUTHORIZED</span>
          <span className="mono" data-testid="live-trading-not-authorized" style={pill("#FF5A5A")}>LIVE TRADING NOT AUTHORIZED</span>
        </div>

        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
          <Button data-testid="load-dashboard" onClick={() => load("/tg/provider-canary-planning/dashboard", setDash)}>
            Planning Overview
          </Button>
          <Button data-testid="load-verdict" onClick={() => load("/tg/provider-canary-planning/verdict", setVerdict)}>
            Certification
          </Button>
          <Button data-testid="load-rankings" onClick={() => load("/tg/provider-canary-planning/rankings", setRank)}>
            Candidate Ranking
          </Button>
          <Button data-testid="load-preferred" onClick={() => load("/tg/provider-canary-planning/preferred", setPreferred)}>
            Preferred Provider
          </Button>
          <Button data-testid="load-fallback" onClick={() => load("/tg/provider-canary-planning/fallback", setFallback)}>
            Fallback Provider
          </Button>
          <Button data-testid="load-sources" onClick={() => load("/tg/provider-canary-planning/sources", setSources)}>
            Evidence Sources
          </Button>
          <Button data-testid="load-capabilities" onClick={() => load("/tg/provider-canary-planning/capabilities", setCaps)}>
            Capability Map
          </Button>
          <Button data-testid="load-scopes" onClick={() => load("/tg/provider-canary-planning/scopes", setScopes)}>
            Scopes
          </Button>
          <Button data-testid="load-eligibility" onClick={() => load("/tg/provider-canary-planning/eligibility", setElig)}>
            Eligibility Review
          </Button>
          <Button data-testid="load-terms" onClick={() => load("/tg/provider-canary-planning/terms", setTerms)}>
            Terms Review
          </Button>
          <Button data-testid="load-canary" onClick={() => load("/tg/provider-canary-planning/canary", setCanary)}>
            Canary Architecture
          </Button>
          <Button data-testid="load-credential" onClick={() => load("/tg/provider-canary-planning/credential-ceremony", setCred)}>
            Credential Ceremony
          </Button>
          <Button data-testid="load-acceptance" onClick={() => load("/tg/provider-canary-planning/acceptance", setAccept)}>
            Acceptance Criteria
          </Button>
          <Button data-testid="load-abort" onClick={() => load("/tg/provider-canary-planning/abort", setAbort)}>
            Abort Triggers
          </Button>
          <Button data-testid="load-owner" onClick={() => load("/tg/provider-canary-planning/owner-package", setOwner)}>
            Owner Review Package
          </Button>
          <Button data-testid="load-network" onClick={() => load("/tg/provider-canary-planning/network-policy", setNet)}>
            Network Policy
          </Button>
          <Button data-testid="load-security" onClick={() => load("/tg/provider-canary-planning/security/scan", setSec, "POST")}>
            Security Scan
          </Button>
          <Button data-testid="try-owner-signoff" onClick={() => load("/tg/provider-canary-planning/owner-signoff", setOwnerBlock, "POST")}>
            Try Owner Sign-off (must fail)
          </Button>
          <Button data-testid="try-activate" onClick={() => load("/tg/provider-canary-planning/canary/activate", setActivateBlock, "POST")}>
            Try Activate Canary (must fail)
          </Button>
          <Button data-testid="try-credentials" onClick={() => load("/tg/provider-canary-planning/credentials", setCredBlock, "POST", { api_key: "should-reject" })}>
            Try Credentials (must fail)
          </Button>
        </div>

        <LoadError error={error} />

        <Section title="Planning Overview" testid="section-dashboard" data={dash} />
        <Section title="Certification" testid="section-verdict" data={verdict} />
        <Section title="Candidate Ranking" testid="section-rankings" data={rank} />
        <Section title="Preferred Provider" testid="section-preferred" data={preferred} />
        <Section title="Fallback Provider" testid="section-fallback" data={fallback} />
        <Section title="Evidence Sources" testid="section-sources" data={sources} />
        <Section title="Capability Map / Endpoints" testid="section-capabilities" data={caps} />
        <Section title="Proposed & Forbidden Scopes" testid="section-scopes" data={scopes} />
        <Section title="Eligibility Review" testid="section-eligibility" data={elig} />
        <Section title="Terms and Data Governance" testid="section-terms" data={terms} />
        <Section title="Canary Architecture" testid="section-canary" data={canary} />
        <Section title="Credential Ceremony" testid="section-credential" data={cred} />
        <Section title="Acceptance Criteria" testid="section-acceptance" data={accept} />
        <Section title="Abort Triggers" testid="section-abort" data={abort} />
        <Section title="Owner Review Package" testid="section-owner" data={owner} />
        <Section title="Network Policy" testid="section-network" data={net} />
        <Section title="Security / Isolation" testid="section-security" data={sec} />
        <Section title="Owner Sign-off Block" testid="section-owner-block" data={ownerBlock} />
        <Section title="Canary Activation Block" testid="section-activate-block" data={activateBlock} />
        <Section title="Credential Rejection" testid="section-cred-block" data={credBlock} />

        <Card style={{ marginTop: 16 }}>
          <Heading level={3}>Evidence Centre</Heading>
          <Text className="mono" data-testid="evidence-path">
            docs/trading/m240_m247_evidence/
          </Text>
          <Text data-testid="authority-locks" className="mono" style={{ display: "block", marginTop: 8 }}>
            REAL_CONNECTIVITY_AUTHORIZED=false · CREDENTIAL_PROVISIONING_AUTHORIZED=false · CANARY_ACTIVATION_AUTHORIZED=false · LIVE_TRADING_AUTHORIZED=false
          </Text>
        </Card>
      </SignInGate>
    </div>
  );
}

function Section({ title, testid, data }) {
  if (!data) return null;
  return (
    <Card style={{ marginTop: 12 }} data-testid={testid}>
      <Heading level={3}>{title}</Heading>
      <pre className="mono" style={{ whiteSpace: "pre-wrap", fontSize: 12, maxHeight: 320, overflow: "auto" }}>
        {JSON.stringify(data, null, 2)}
      </pre>
    </Card>
  );
}

function pill(bg) {
  return {
    background: bg,
    color: "#0b0b0b",
    padding: "4px 10px",
    borderRadius: 999,
    fontSize: 11,
    fontWeight: 700,
  };
}
