"use client";
import { useState } from "react";
import { useParams } from "next/navigation";
import { Panel, Eyebrow, Pill } from "@/components/ui";
import MissionNav from "@/components/MissionNav";

const API_BASE = process.env.NEXT_PUBLIC_SAATHI_API || "http://localhost:8765";

export default function WebsiteIntelligence() {
  const { id } = useParams();
  const [url, setUrl] = useState("");
  const [compareUrl, setCompareUrl] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const analyze = async () => {
    if (!url.trim()) return;
    setLoading(true);
    setError("");
    try {
      const r = await fetch(`${API_BASE}/api/v1/missions/${id}/website`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ url: url.trim(), compare_url: compareUrl.trim() }),
      });
      const d = await r.json();
      if (!d.ok) throw new Error(d.error || "Analysis failed");
      setResult(d);
    } catch (e) {
      setError(e.message || "Unable to analyze website");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <MissionNav />
      <div className="page" style={{ maxWidth: 1080, margin: "0 auto", paddingBottom: 60 }}>
        <Eyebrow>Website Intelligence</Eyebrow>
        <div style={{ fontSize: 24, fontWeight: 600, margin: "8px 0 20px" }}>
          Analyze & Design
        </div>
        <p style={{ color: "var(--color-ink-400)", fontSize: 14, marginBottom: 24, lineHeight: 1.5 }}>
          Paste a website URL to analyze its technology stack, UX patterns, SEO signals, and design patterns.
          Saathi will generate an original Mission-branded design system based on the analysis.
        </p>

        <div style={{ display: "flex", gap: 12, marginBottom: 24, flexWrap: "wrap" }}>
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && analyze()}
            placeholder="https://example.com"
            style={{
              flex: 1,
              minWidth: 280,
              padding: "12px 16px",
              borderRadius: 12,
              border: "1px solid rgba(255,255,255,0.12)",
              background: "rgba(255,255,255,0.05)",
              color: "inherit",
              fontSize: 14,
            }}
          />
          <input
            value={compareUrl}
            onChange={(e) => setCompareUrl(e.target.value)}
            placeholder="Compare URL (optional)"
            style={{
              flex: 1,
              minWidth: 280,
              padding: "12px 16px",
              borderRadius: 12,
              border: "1px solid rgba(255,255,255,0.12)",
              background: "rgba(255,255,255,0.05)",
              color: "inherit",
              fontSize: 14,
            }}
          />
          <button
            onClick={analyze}
            disabled={loading || !url.trim()}
            style={{
              padding: "12px 24px",
              borderRadius: 12,
              border: "none",
              fontSize: 14,
              fontWeight: 600,
              cursor: "pointer",
              background: loading ? "rgba(255,255,255,0.10)" : "radial-gradient(circle at 38% 35%, #ffffff, #9fc0ff)",
              color: loading ? "var(--color-ink-400)" : "#0A1120",
              opacity: loading ? 0.6 : 1,
            }}
          >
            {loading ? "Analyzing…" : "Analyze"}
          </button>
        </div>

        {error && (
          <Panel style={{ padding: 20, marginBottom: 20, border: "1px solid rgba(255,82,82,0.3)" }}>
            <div style={{ color: "#FF5252", fontSize: 14 }}>{error}</div>
          </Panel>
        )}

        {result && (
          <>
            {result.design_system && (
              <Panel style={{ padding: 24, marginBottom: 20 }}>
                <Eyebrow>Design System</Eyebrow>
                <div style={{ marginTop: 16, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
                  <div>
                    <div style={{ fontSize: 11, opacity: 0.5, marginBottom: 8 }}>COLORS</div>
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                      {(result.design_system.colors || []).map((c) => (
                        <div key={c} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                          <div style={{ width: 24, height: 24, borderRadius: 6, background: c, border: "1px solid rgba(255,255,255,0.15)" }} />
                          <span className="mono" style={{ fontSize: 10 }}>{c}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div>
                    <div style={{ fontSize: 11, opacity: 0.5, marginBottom: 8 }}>TYPOGRAPHY</div>
                    <div style={{ fontSize: 13, color: "var(--color-ink-200)" }}>
                      {(result.design_system.fonts || []).join(", ") || "Not detected"}
                    </div>
                  </div>
                </div>
              </Panel>
            )}

            {result.blueprint && (
              <Panel style={{ padding: 24, marginBottom: 20 }}>
                <Eyebrow>Frontend Blueprint</Eyebrow>
                <div style={{ marginTop: 16 }}>
                  <div style={{ fontSize: 13, color: "var(--color-ink-200)", lineHeight: 1.6, whiteSpace: "pre-wrap" }}>
                    {typeof result.blueprint === "string" ? result.blueprint : JSON.stringify(result.blueprint, null, 2)}
                  </div>
                </div>
              </Panel>
            )}

            {result.tech_stack && (
              <Panel style={{ padding: 24, marginBottom: 20 }}>
                <Eyebrow>Technology Stack</Eyebrow>
                <div style={{ marginTop: 16, display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {(result.tech_stack || []).map((tech) => (
                    <Pill key={tech} color="#8FB4FF" filled={0.16}>{tech}</Pill>
                  ))}
                </div>
              </Panel>
            )}

            {result.seo && (
              <Panel style={{ padding: 24, marginBottom: 20 }}>
                <Eyebrow>SEO Signals</Eyebrow>
                <div style={{ marginTop: 16, display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 16 }}>
                  {Object.entries(result.seo).map(([key, val]) => (
                    <div key={key} className="glass-soft" style={{ padding: 14 }}>
                      <div style={{ fontSize: 10, opacity: 0.5, textTransform: "capitalize" }}>{key.replace(/_/g, " ")}</div>
                      <div style={{ fontSize: 14, marginTop: 4, color: "var(--color-ink-100)" }}>
                        {typeof val === "object" ? JSON.stringify(val) : String(val)}
                      </div>
                    </div>
                  ))}
                </div>
              </Panel>
            )}

            {result.page_structure && (
              <Panel style={{ padding: 24, marginBottom: 20 }}>
                <Eyebrow>Page Structure</Eyebrow>
                <div style={{ marginTop: 16 }}>
                  <div style={{ fontSize: 13, color: "var(--color-ink-200)", lineHeight: 1.6, whiteSpace: "pre-wrap" }}>
                    {typeof result.page_structure === "string" ? result.page_structure : JSON.stringify(result.page_structure, null, 2)}
                  </div>
                </div>
              </Panel>
            )}
          </>
        )}
      </div>
    </div>
  );
}
