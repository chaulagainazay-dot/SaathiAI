"use client";
import { useState } from "react";
import { useParams } from "next/navigation";
import { Panel, Eyebrow, Pill } from "@/components/ui";
import MissionNav from "@/components/MissionNav";

const API_BASE = process.env.NEXT_PUBLIC_SAATHI_API || "http://localhost:8765";

const REF_TYPES = [
  { key: "github", label: "GitHub Repo", placeholder: "https://github.com/owner/repo" },
  { key: "website", label: "Website", placeholder: "https://example.com" },
  { key: "documentation", label: "Documentation", placeholder: "https://docs.example.com" },
  { key: "pdf", label: "PDF", placeholder: "https://example.com/document.pdf" },
  { key: "figma", label: "Figma", placeholder: "https://figma.com/file/..." },
  { key: "youtube", label: "YouTube", placeholder: "https://youtube.com/watch?v=..." },
];

export default function ReferenceIntelligence() {
  const { id } = useParams();
  const [urls, setUrls] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const analyze = async () => {
    if (!urls.trim()) return;
    setLoading(true);
    setError("");
    try {
      const r = await fetch(`${API_BASE}/api/v1/missions/${id}/reference`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ urls: urls.split("\n").map((u) => u.trim()).filter(Boolean) }),
      });
      const d = await r.json();
      if (!d.ok) throw new Error(d.error || "Analysis failed");
      setResult(d);
    } catch (e) {
      setError(e.message || "Unable to analyze references");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <MissionNav />
      <div className="page" style={{ maxWidth: 1080, margin: "0 auto", paddingBottom: 60 }}>
        <Eyebrow>Reference Intelligence</Eyebrow>
        <div style={{ fontSize: 24, fontWeight: 600, margin: "8px 0 20px" }}>
          Research Library
        </div>
        <p style={{ color: "var(--color-ink-400)", fontSize: 14, marginBottom: 24, lineHeight: 1.5 }}>
          Paste URLs to analyze references. The system will categorize, store, and link them to the Knowledge Graph
          and Research Library. One reference per line.
        </p>

        <div style={{ display: "flex", gap: 12, marginBottom: 24, flexWrap: "wrap" }}>
          <textarea
            value={urls}
            onChange={(e) => setUrls(e.target.value)}
            placeholder={`Paste one URL per line:
https://github.com/owner/repo
https://example.com
https://docs.example.com/guide`}
            rows={5}
            style={{
              flex: 1,
              minWidth: 400,
              padding: "12px 16px",
              borderRadius: 12,
              border: "1px solid rgba(255,255,255,0.12)",
              background: "rgba(255,255,255,0.05)",
              color: "inherit",
              fontSize: 14,
              resize: "vertical",
            }}
          />
          <button
            onClick={analyze}
            disabled={loading || !urls.trim()}
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
              alignSelf: "flex-start",
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
            {result.references && (
              <Panel style={{ padding: 24, marginBottom: 20 }}>
                <Eyebrow>Analyzed References</Eyebrow>
                <div style={{ marginTop: 16, display: "flex", flexDirection: "column", gap: 12 }}>
                  {(result.references || []).map((ref) => (
                    <div key={ref.url} className="glass-soft" style={{ padding: 16 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
                        <Pill color="#8FB4FF" filled={0.16}>{ref.type || "reference"}</Pill>
                        <a href={ref.url} target="_blank" rel="noopener noreferrer" style={{ fontSize: 13, color: "#8FB4FF", textDecoration: "none" }}>
                          {ref.url}
                        </a>
                      </div>
                      {ref.title && <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>{ref.title}</div>}
                      {ref.summary && <div style={{ fontSize: 13, color: "var(--color-ink-400)", lineHeight: 1.5 }}>{ref.summary}</div>}
                      {ref.tags && (
                        <div style={{ display: "flex", gap: 6, marginTop: 8, flexWrap: "wrap" }}>
                          {(ref.tags || []).map((tag) => (
                            <span key={tag} className="mono" style={{ fontSize: 10, padding: "2px 8px", borderRadius: 999, background: "rgba(255,255,255,0.08)", color: "var(--color-ink-400)" }}>
                              {tag}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </Panel>
            )}

            {result.knowledge_linked && (
              <Panel style={{ padding: 24, marginBottom: 20 }}>
                <Eyebrow>Knowledge Graph Linked</Eyebrow>
                <div style={{ marginTop: 16 }}>
                  <div style={{ fontSize: 13, color: "var(--color-ink-200)", lineHeight: 1.6 }}>
                    {(result.knowledge_linked || []).length} nodes added to the Knowledge Graph.
                  </div>
                </div>
              </Panel>
            )}

            {result.timeline_entry && (
              <Panel style={{ padding: 24, marginBottom: 20 }}>
                <Eyebrow>Timeline Entry</Eyebrow>
                <div style={{ marginTop: 16 }}>
                  <div style={{ fontSize: 13, color: "var(--color-ink-200)", lineHeight: 1.6 }}>
                    Reference analysis recorded in Mission Timeline.
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
